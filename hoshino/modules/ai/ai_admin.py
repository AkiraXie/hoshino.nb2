"""AI 管理插件：provider / model / scope 配置与用量查询（**仅超级用户可用**）。

模型管理语义：
- ``ai model``：显示当前使用的文本/多模态模型（含来源）与操作提示。
- ``ai model list``：调用 provider API 获取**真实可用模型列表**（本地不存 model-list）。
- ``ai model set <模型>``：设置文本模型（默认槽位）；``ai model set vision <模型>``
  设置多模态模型；``vision none`` 禁用多模态。设置前实时校验模型在 API 可用列表内，
  设置/禁用后回显当前两个生效模型。
- ``ai model reset [text|vision]``：清除本群覆盖，回退 provider 默认。

provider 管理语义：
- ``ai provider``：显示全局默认与当前群绑定 + 操作提示。
- ``ai provider set <id>``（兼容 ``use``）：绑定当前群；``default <id>`` 设全局默认；
  ``reset`` 清除绑定；``list`` 列出已配置。
- ``ai setup <id> --url <url> --key <key> [--text <m>] [--vision <m>]``：
  一键配置：新增/更新 provider + 设默认 + 绑定当前群（唯一新增入口）。
- ``ai provider remove <id>``：删除 provider。

其余：``ai status``、``ai stats [provider_id]``、``ai clear [scope]``、
``ai contexts [scope]``、``ai tools ...``、``ai persona ...``。
"""

from __future__ import annotations

from nonebot.adapters import Bot, Event

from hoshino.core.permission import SUPERUSER
from hoshino.platform import (
    event_scope_key,
    get_group_id,
    get_user_id,
    group_scope_key,
    platform_key,
    send_to_event,
)
from hoshino.platform.depends import ParamText
from hoshino.platform.superuser import is_superuser

from hoshino.ai import (
    deps,
    metrics,
    persona,
    provider,
    providers,
    sessions,
    store,
    tools,
)
from hoshino.ai.base import get_config
from hoshino.ai.config import mask_url
from hoshino.ai.provider import ProviderRecord
from hoshino.core.service import Service

# ai_admin 服务：管理命令（ai / ai task）统一挂此服务，默认开启（仅 SUPERUSER 可用）。
sv = Service("ai_admin", enable_on_default=True, visible=False)

USAGE = (
    "AI 管理（仅超级用户可用）：\n"
    "快速上手：\n"
    "  ai setup <id> --url <u> --key <k> [--text <m>] [--vision <m>]  一键配置 provider\n"
    "  ai model              查看当前文本/多模态模型\n"
    "  ai model list         获取真实可用模型（provider API）\n"
    "  ai model set <模型>   设置文本模型（默认）；ai model set vision <模型> 设多模态\n"
    "  ai provider           查看当前 provider\n"
    "  ai provider set <id>  绑定当前群到指定 provider\n"
    "其他：\n"
    "  ai provider list / default <id> / reset / remove\n"
    "  ai model reset [text|vision] / ai status / ai stats [provider_id]\n"
    "  ai clear [scope] / ai contexts [scope] / ai tools ... / ai persona ...\n"
    "  ai task research|plan|status|list|approve|deny|cancel|workspaces\n"
    "用 ai setup / ai persona 查看参数说明。"
)

_SETUP_USAGE = (
    "用法：ai setup <provider_id> --url <url> --key <key> [--text <m>] [--vision <m>]\n"
    "一步完成：新增/更新 provider（openai_chat 兼容）、设全局默认、绑定当前群、"
    "把 --text/--vision 设为默认模型；之后 ai model / ai status 查看生效配置。"
)

_TOOLS_USAGE = (
    "AI 工具管理（仅超级用户）：\n"
    "  ai tools list [chat|task]           查看可用工具\n"
    "  ai tools on|off <类别> [chat|task]  开启/关闭类别（默认 chat）\n"
    "类别：core / computer / bot / web / skill"
)


def _tool_name(tool) -> str:
    return getattr(tool, "name", None) or getattr(tool, "__name__", None) or "?"


_PERSONA_USAGE = (
    "用法：\n"
    "  ai persona list\n"
    "  ai persona show <name>\n"
    "  ai persona use <name>   绑定当前 scope\n"
    "  ai persona reset        解除当前 scope 绑定\n"
    "  ai persona global <name>|off   设置/清除全局\n"
    "  ai persona delete <name>       删除\n"
    "创建/更新 persona 请直接让 AI 使用 persona_manage 工具（对话中说明即可）。"
)

_MODEL_USAGE = (
    "用法：\n"
    "  ai model                    查看当前文本/多模态模型\n"
    "  ai model list               获取真实可用模型（provider API）\n"
    "  ai model set <模型>         设置文本模型（默认槽位）\n"
    "  ai model set vision <模型>  设置多模态模型\n"
    "  ai model set vision none    禁用多模态\n"
    "  ai model reset [text|vision] 清除本群覆盖\n"
    "示例：ai model set deepseek-v4-flash；ai model set vision gpt-5.6-luna"
)

# 全部 ai 管理命令仅 SUPERUSER 可用；only_group=False 让私聊也能触发，从而在
# handler 内给出“私聊不允许”的明确提示，而不是静默无响应。
aicmd = sv.on_command("ai", permission=SUPERUSER, compact=False, only_group=False)


@aicmd.handle()
async def _(bot: Bot, event: Event, text: str = ParamText()):
    args = text.strip().split()
    if not args:
        # 裸 `ai`：直接给状态总览（含看图引导），比命令清单更自然。
        await _handle_status(bot, event)
        await send_to_event(bot, event, "更多命令：`ai help` 查看完整说明。")
        return
    sub, rest = args[0], args[1:]
    if sub in ("help", "?"):
        await send_to_event(bot, event, USAGE)
    elif sub == "setup":
        await _handle_setup(bot, event, rest)
    elif sub == "provider":
        await _handle_provider(bot, event, rest)
    elif sub == "model":
        await _handle_model(bot, event, rest)
    elif sub == "status":
        await _handle_status(bot, event)
    elif sub == "stats":
        await _handle_stats(bot, event, rest)
    elif sub == "clear":
        await _handle_clear(bot, event, rest)
    elif sub == "contexts":
        await _handle_contexts(bot, event, rest)
    elif sub == "tools":
        await _handle_tools(bot, event, rest)
    elif sub == "persona":
        await _handle_persona(bot, event, rest)
    else:
        await send_to_event(bot, event, USAGE)


def _parse_flags(args: list[str]) -> dict[str, str]:
    """把 ``--key value`` 解析成 dict（值缺失记空串）。"""
    opts: dict[str, str] = {}
    index = 0
    while index < len(args):
        arg = args[index]
        if arg.startswith("--"):
            key = arg[2:].replace("-", "_")
            if index + 1 < len(args) and not args[index + 1].startswith("--"):
                value = args[index + 1]
                index += 2
            else:
                value = ""
                index += 1
            if value in ('""', "''"):
                value = ""
            opts[key] = value
        else:
            index += 1
    return opts


def _require_superuser(bot: Bot, event: Event) -> bool:
    user_id = get_user_id(event)
    return bool(user_id is not None and is_superuser(bot, user_id))


async def _handle_provider(bot: Bot, event: Event, args: list[str]) -> None:
    if not args:
        await _provider_status(bot, event)
        return
    action, rest = args[0], args[1:]
    config = get_config()
    if action == "list":
        await _provider_list(bot, event, config)
    elif action in ("set", "use"):
        await _provider_set(bot, event, rest)
    elif action == "default":
        await _provider_default(bot, event, rest, config)
    elif action == "reset":
        await _provider_reset(bot, event)
    elif action == "remove":
        await _provider_remove(bot, event, rest, config)
    else:
        await send_to_event(bot, event, USAGE)


async def _provider_status(bot: Bot, event: Event) -> None:
    """`ai provider`：当前 provider（全局默认 + 本群绑定）+ 操作提示。"""
    config = get_config()
    scope_key = event_scope_key(bot, event)
    bound = store.get_scope_provider(scope_key) if scope_key else None
    lines = [
        f"全局默认 provider：`{config.default}`"
        if config.default
        else "全局默认 provider：未设置",
        f"本群绑定：`{bound}`" if bound else "本群绑定：无（回退全局默认）",
        "设本群：ai provider set <id>；设全局默认：ai provider default <id>",
        "看已配置：ai provider list；看模型：ai model list",
    ]
    await send_to_event(bot, event, "\n".join(lines))


async def _provider_list(bot: Bot, event: Event, config) -> None:
    records = provider.list_providers()
    if not records:
        await send_to_event(bot, event, "未配置任何 provider。")
        return
    lines = ["已配置的 provider："]
    for record in records:
        mark = " ← 默认" if record.id == config.default else ""
        vision = record.default_vision_model or "（无）"
        lines.append(
            f"- `{record.id}` kind={record.kind} "
            f"text={record.default_text_model or '-'} "
            f"vision={vision} url={mask_url(record.url)}{mark}"
        )
    lines.append("模型列表用 `ai model list` 实时获取。")
    await send_to_event(bot, event, "\n".join(lines))


async def _provider_default(bot: Bot, event: Event, args: list[str], config) -> None:
    if not _require_superuser(bot, event):
        await send_to_event(bot, event, "仅 SUPERUSER 可设置全局默认 provider。")
        return
    if not args:
        await send_to_event(bot, event, "用法：ai provider default <id>")
        return
    pid = args[0]
    if not provider.has_provider(pid):
        await send_to_event(bot, event, f"provider `{pid}` 不存在。")
        return
    store.set_global_value("default_provider", pid)
    await send_to_event(bot, event, f"已设置全局默认 provider：`{pid}`")


async def _provider_set(bot: Bot, event: Event, args: list[str]) -> None:
    """`ai provider set <id>`：把当前群 scope 绑定到指定 provider。"""
    gid = get_group_id(event)
    if gid is None:
        await send_to_event(bot, event, "私聊不允许切换 provider。")
        return
    if not args:
        await send_to_event(bot, event, "用法：ai provider set <id>")
        return
    pid = args[0]
    if not provider.has_provider(pid):
        await send_to_event(bot, event, f"provider `{pid}` 不存在。")
        return
    scope_key = group_scope_key(gid, platform=platform_key(bot))
    store.set_scope_provider(scope_key, pid, updated_by=str(get_user_id(event) or ""))
    await send_to_event(bot, event, f"本群已切换到 provider `{pid}`。")


async def _provider_reset(bot: Bot, event: Event) -> None:
    gid = get_group_id(event)
    if gid is None:
        await send_to_event(bot, event, "私聊不允许重置 provider。")
        return
    scope_key = group_scope_key(gid, platform=platform_key(bot))
    cleared = store.clear_scope_provider(scope_key)
    if cleared:
        await send_to_event(bot, event, "已清除本群 provider 绑定，回退全局默认。")
    else:
        await send_to_event(bot, event, "本群当前没有绑定 provider。")


async def _handle_setup(bot: Bot, event: Event, args: list[str]) -> None:
    """一键配置：新增/更新 provider + 设全局默认 + 绑定当前群。"""
    if not _require_superuser(bot, event):
        await send_to_event(bot, event, "仅 SUPERUSER 可配置 provider。")
        return
    if not args:
        await send_to_event(bot, event, _SETUP_USAGE)
        return
    pid = args[0]
    opts = _parse_flags(args[1:])
    if not opts.get("url") or not opts.get("key"):
        await send_to_event(bot, event, "setup 需要 --url 与 --key。")
        return

    existed = provider.has_provider(pid)
    provider.upsert_provider(
        ProviderRecord(
            id=pid,
            url=opts.get("url", ""),
            key=opts.get("key", ""),
            kind="openai_chat",
            default_text_model=opts.get("text", ""),
            default_vision_model=opts.get("vision", ""),
        )
    )
    providers.clear_agent_cache()

    lines = [f"已{'更新' if existed else '新增'} provider `{pid}`。"]
    store.set_global_value("default_provider", pid)
    lines.append("已设为全局默认 provider。")
    gid = get_group_id(event)
    if gid is not None:
        scope_key = group_scope_key(gid, platform=platform_key(bot))
        store.set_scope_provider(
            scope_key, pid, updated_by=str(get_user_id(event) or "")
        )
        lines.append("已绑定当前群。")
    if opts.get("text"):
        lines.append(f"文本模型：`{opts['text']}`。")
    if opts.get("vision"):
        lines.append(f"视觉模型：`{opts['vision']}`（可看图）。")
    else:
        lines.append(
            "视觉模型未设置：看图需配置 vision 模型，可 `ai model set vision <模型>`。"
        )
    lines.append("用 `ai status` 查看生效配置。")
    await send_to_event(bot, event, "\n".join(lines))


async def _provider_remove(bot: Bot, event: Event, args: list[str], config) -> None:
    if not _require_superuser(bot, event):
        await send_to_event(bot, event, "仅 SUPERUSER 可删除 provider。")
        return
    if not args:
        await send_to_event(bot, event, "用法：ai provider remove <id>")
        return
    pid = args[0]
    if pid == config.default:
        await send_to_event(
            bot, event, "当前默认 provider 不允许直接删除，请先修改 default。"
        )
        return
    if not provider.has_provider(pid):
        await send_to_event(bot, event, f"provider `{pid}` 不存在。")
        return
    store.clear_provider_references(pid)
    provider.remove_provider(pid)
    providers.clear_agent_cache()
    await send_to_event(bot, event, f"已删除 provider `{pid}`。")


# ------------------------------------------------------------ scope models


async def _handle_model(bot: Bot, event: Event, args: list[str]) -> None:
    if not args:
        await _model_status(bot, event)
        return
    action, rest = args[0], args[1:]
    if action in ("show", "status"):
        await _model_status(bot, event)
        return
    if action == "list":
        await _model_list(bot, event)
        return
    gid = get_group_id(event)
    if gid is None:
        await send_to_event(bot, event, "模型设置仅限群聊。")
        return
    scope_key = group_scope_key(gid, platform=platform_key(bot))
    if action == "set":
        await _model_set(bot, event, scope_key, rest)
    elif action == "reset":
        await _model_reset(bot, event, scope_key, rest)
    else:
        await _model_status(bot, event)


async def _scope_provider_id(scope_key: str, config) -> str | None:
    """当前 scope 的有效 provider id（scope 绑定 > 默认），不存在返回 None。"""
    bound = store.get_scope_provider(scope_key)
    if bound and provider.has_provider(bound):
        return bound
    if config.default and provider.has_provider(config.default):
        return config.default
    return None


async def _model_status(bot: Bot, event: Event) -> None:
    """`ai model`：当前使用的文本/多模态模型（含来源）+ 操作提示。"""
    config = get_config()
    scope_key = event_scope_key(bot, event)
    bound = store.get_scope_provider(scope_key) if scope_key else None
    pid = await _scope_provider_id(scope_key, config) if scope_key else None
    if pid is None:
        await send_to_event(
            bot,
            event,
            "当前没有可用 provider：`ai provider list` 查看，`ai provider set <id>` 绑定。",
        )
        return
    text_model, vision_model = provider.resolve_models(scope_key, pid)
    overrides = store.get_scope_model_overrides(scope_key or "")
    source_text = "本群覆盖" if overrides["text_model"] else "provider 默认"
    source_vision = (
        "本群覆盖"
        if overrides["vision_model"]
        else (
            "显式禁用"
            if overrides["vision_model"] == provider.VISION_DISABLED
            else "provider 默认"
        )
    )
    lines = [
        f"provider：`{pid}`" + ("" if not bound else "（本群绑定）"),
        f"文本模型：`{text_model or '（未设置）'}`（{source_text}）",
        f"多模态模型：`{vision_model or '（未设置）'}`（{source_vision}）",
        "改文本：ai model set <模型>；改多模态：ai model set vision <模型>",
        "看可用模型：ai model list",
    ]
    await send_to_event(bot, event, "\n".join(lines))


async def _model_list(bot: Bot, event: Event) -> None:
    """`ai model list`：调用 provider API 获取真实可用模型列表。"""
    config = get_config()
    scope_key = event_scope_key(bot, event)
    pid = await _scope_provider_id(scope_key, config) if scope_key else None
    if pid is None:
        await send_to_event(bot, event, "当前没有可用 provider，无法获取模型列表。")
        return
    record = provider.get_provider(pid)
    models = await provider.fetch_available_models(
        record, proxy=config.proxy, verify=config.web_fetch_verify_ssl
    )
    if not models:
        await send_to_event(
            bot, event, f"获取 provider `{pid}` 的模型列表失败（网络或端点不支持）。"
        )
        return
    text_model, vision_model = provider.resolve_models(scope_key, pid)
    lines = [f"provider `{pid}` 可用模型（{len(models)} 个，来自 API）："]
    for model in models:
        marks = []
        if model == text_model:
            marks.append("当前文本")
        if model == vision_model:
            marks.append("当前多模态")
        lines.append(f"- {model}" + (f"（{'、'.join(marks)}）" if marks else ""))
    lines.append("设置：ai model set <模型>（文本）| ai model set vision <模型>")
    await send_to_event(bot, event, "\n".join(lines))


async def _model_set(bot: Bot, event: Event, scope_key: str, args: list[str]) -> None:
    """`ai model set [text|vision] <模型>`：默认改 text；实时校验后在 provider API 可用列表内。

    设置/禁用后回显当前两个生效模型。
    """
    if not args:
        await send_to_event(bot, event, _MODEL_USAGE)
        return
    slot = "text"
    model = args[0]
    if args[0] in ("text", "vision"):
        if len(args) != 2:
            await send_to_event(bot, event, "用法：ai model set [text|vision] <模型>")
            return
        slot, model = args[0], args[1]
    elif len(args) != 1:
        await send_to_event(bot, event, "用法：ai model set [text|vision] <模型>")
        return

    config = get_config()
    pid = await _scope_provider_id(scope_key, config)
    if pid is None:
        await send_to_event(
            bot,
            event,
            "本群没有可用 provider：`ai provider list` 查看，`ai provider set <id>` 绑定。",
        )
        return
    if slot == "vision" and model == provider.VISION_DISABLED:
        store.set_scope_model_override(
            scope_key, "vision", model, updated_by=str(get_user_id(event) or "")
        )
        await _echo_models(bot, event, scope_key, pid, "（多模态已禁用）")
        return

    record = provider.get_provider(pid)
    available = await provider.fetch_available_models(
        record, proxy=config.proxy, verify=config.web_fetch_verify_ssl
    )
    warning = ""
    if available is not None:
        if model not in available:
            sample = "、".join(f"`{m}`" for m in available[:20])
            await send_to_event(
                bot,
                event,
                f"模型 `{model}` 不在 provider `{pid}` 的可用列表中（API 获取）。\n"
                f"可用：{sample}{'…' if len(available) > 20 else ''}\n"
                "全部可用模型：ai model list",
            )
            return
    else:
        warning = "（无法连接 provider 校验，已直接设置）"

    store.set_scope_model_override(
        scope_key, slot, model, updated_by=str(get_user_id(event) or "")
    )
    note = (
        "（vision 模型需真正支持多模态，若识别失败请换模型）"
        if slot == "vision"
        else ""
    )
    await _echo_models(bot, event, scope_key, pid, warning + note)


async def _model_reset(bot: Bot, event: Event, scope_key: str, args: list[str]) -> None:
    """`ai model reset [text|vision]`：清除覆盖回退 provider 默认，并回显。"""
    if args and args[0] not in ("text", "vision"):
        await send_to_event(bot, event, "用法：ai model reset [text|vision]")
        return
    slot = args[0] if args else None
    cleared = store.clear_scope_model_override(scope_key, slot)
    if not cleared:
        await send_to_event(
            bot, event, "本群当前没有模型覆盖。" if slot is None else "该槽位没有覆盖。"
        )
        return
    label = (
        "纯文本模型"
        if slot == "text"
        else ("多模态模型" if slot == "vision" else "模型")
    )
    config = get_config()
    pid = await _scope_provider_id(scope_key, config)
    if pid is not None:
        await _echo_models(
            bot, event, scope_key, pid, f"（已清除本群{label}覆盖，回退 provider 默认）"
        )
    else:
        await send_to_event(bot, event, f"已清除本群{label}覆盖。")


async def _echo_models(
    bot: Bot, event: Event, scope_key: str, pid: str, extra: str = ""
) -> None:
    """设置/重置后回显当前两个生效模型（含操作提示）。"""
    text_model, vision_model = provider.resolve_models(scope_key, pid)
    await send_to_event(
        bot,
        event,
        f"当前文本模型：`{text_model or '（未设置）'}`；"
        f"多模态模型：`{vision_model or '（未设置）'}`{extra}\n"
        "改：ai model set <模型>（文本）| ai model set vision <模型>",
    )


async def _handle_status(bot: Bot, event: Event) -> None:
    """`ai status` / 裸 `ai`：只显示当前 provider 与文本/多模态模型。

    刻意不暴露代理、渲染、历史长度等配置细节（看板保持极简，且不泄露内网配置）。
    """
    config = get_config()
    scope_key = event_scope_key(bot, event)
    bound = store.get_scope_provider(scope_key) if scope_key else None
    provider_id = bound or config.default
    if not provider_id or not provider.has_provider(provider_id):
        await send_to_event(
            bot,
            event,
            "当前没有可用 provider：`ai provider list` 查看，`ai provider set <id>` 绑定。",
        )
        return
    text_model, vision_model = provider.resolve_models(scope_key, provider_id)
    source = "（本群绑定）" if bound else "（全局默认）"
    lines = [
        f"当前 provider：`{provider_id}`{source}",
        f"文本模型：`{text_model or '（未设置）'}`",
        f"多模态模型：`{vision_model or '（未设置）'}`",
    ]
    await send_to_event(bot, event, "\n".join(lines))


async def _handle_stats(bot: Bot, event: Event, args: list[str]) -> None:
    pid = args[0] if args else None
    if pid is not None and not provider.has_provider(pid):
        await send_to_event(bot, event, f"provider `{pid}` 不存在。")
        return
    aggregate = store.aggregate_usage(provider_id=pid)
    lines = [metrics.format_stats(aggregate, provider_id=pid)]
    rows = store.aggregate_usage_by_model(provider_id=pid)
    if rows:
        lines.append("")
        lines.append(metrics.format_model_stats(rows, provider_id=pid))
    await send_to_event(bot, event, "\n".join(lines))


async def _handle_clear(bot: Bot, event: Event, args: list[str]) -> None:
    manager = sessions.conversation_manager
    if args:
        # 显式指定 scope_key：清空其当前激活对话（ADMIN 即可）。
        cleared = manager.clear_active(args[0])
    else:
        scope_key = event_scope_key(bot, event)
        if scope_key is None:
            await send_to_event(bot, event, "无法解析当前会话 scope。")
            return
        cleared = manager.clear_active(scope_key)
    await send_to_event(
        bot, event, "已清理会话历史。" if cleared else "没有可清理的会话历史。"
    )


async def _handle_contexts(bot: Bot, event: Event, args: list[str]) -> None:
    """只读查看 scope 的对话清单（多对话模型，plan aichat-context-timeout）。"""
    scope_key = args[0] if args else event_scope_key(bot, event)
    if not scope_key:
        await send_to_event(bot, event, "无法解析 scope。")
        return
    summaries = sessions.conversation_manager.list_summaries(scope_key)
    if not summaries:
        await send_to_event(bot, event, f"scope `{scope_key}` 还没有对话。")
        return
    lines = [f"scope `{scope_key}` 的对话："]
    for s in summaries:
        mark = "* " if s["active"] else "- "
        lines.append(f"{mark}{s['name']}（{s['count']} 条消息）")
    await send_to_event(bot, event, "\n".join(lines))


# ------------------------------------------------------------------- tools


async def _handle_tools(bot: Bot, event: Event, args: list[str]) -> None:
    if not args:
        await send_to_event(bot, event, _TOOLS_USAGE)
        return
    action, rest = args[0], args[1:]
    if action == "list":
        await _tools_list(bot, event, rest)
    elif action in ("on", "off"):
        await _tools_set(bot, event, action == "on", rest)
    else:
        await send_to_event(bot, event, _TOOLS_USAGE)


def _list_deps(scope_key: str, surface: str):
    """构造仅用于查询可解析工具的 AgentDeps（无 bot/event）。"""
    return deps.AgentDeps(
        surface=surface,  # type: ignore[arg-type]
        scope_key=scope_key,
        target=deps_target_placeholder(),
        config=get_config(),
        permissions=deps.PermissionSnapshot(),
        bot=None,
        event=None,
        telemetry=deps.Telemetry(provider_id="", scope_key=scope_key, model=""),
    )


def deps_target_placeholder():
    """占位 Target，仅供 ai tools list 展示解析结果用。"""
    from nonebot_plugin_alconna.uniseg import Target

    return Target.group("0")


async def _tools_list(bot: Bot, event: Event, args: list[str]) -> None:
    surface = "chat"
    scope_key = event_scope_key(bot, event)
    remaining = list(args)
    if remaining and remaining[-1] in ("chat", "task"):
        surface = remaining.pop()
    if remaining:
        scope_key = remaining[0]  # 超管可显式查看其它会话
    if not scope_key:
        await send_to_event(bot, event, "无法确定目标会话。")
        return

    where = "本群" if get_group_id(event) is not None else "当前会话"
    resolved = tools.resolve_tools(_list_deps(scope_key, surface))
    surface_hint = "" if surface == "chat" else f"（{surface}）"
    if not resolved:
        await send_to_event(bot, event, f"{where}{surface_hint}没有可用工具。")
        return

    # 按类别分组展示（类别名与工具名保持原始值，便于 on/off 操控）。
    by_category: dict[str, list[str]] = {}
    for tool in resolved:
        by_category.setdefault(tools.tool_category(tool), []).append(_tool_name(tool))

    lines = [f"{where}{surface_hint}可用工具："]
    for category in sorted(by_category):
        lines.append(f"  · {category}：{'、'.join(by_category[category])}")
    await send_to_event(bot, event, "\n".join(lines))


async def _tools_set(bot: Bot, event: Event, enabled: bool, args: list[str]) -> None:
    if not _require_superuser(bot, event):
        await send_to_event(bot, event, "仅超管可修改工具开关。")
        return
    if not args:
        await send_to_event(bot, event, "用法：ai tools on/off <类别> [chat|task]")
        return
    category = args[0]
    rest = args[1:]
    # 第二个参数缺省按 chat；仅当它是 chat/task 时才作为 surface，否则视为显式 scope。
    surface = "chat"
    scope_key: str | None = None
    if rest and rest[0] in ("chat", "task"):
        surface = rest[0]
        rest = rest[1:]
    if rest:
        scope_key = rest[0]
    valid = {"core", "computer", "bot", "web", "skill"}
    if category not in valid:
        await send_to_event(
            bot, event, "类别必须是：core / computer / bot / web / skill。"
        )
        return
    if scope_key is None:
        scope_key = event_scope_key(bot, event)
    if not scope_key:
        await send_to_event(bot, event, "无法确定目标会话。")
        return
    store.set_scope_tool_binding(
        scope_key,
        category,
        surface,
        enabled,
        updated_by=str(get_user_id(event) or ""),
    )
    verb = "开启" if enabled else "关闭"
    surface_hint = "" if surface == "chat" else f"（{surface}）"
    await send_to_event(bot, event, f"已{verb} `{category}`{surface_hint}。")


# ------------------------------------------------------------------ persona


async def _handle_persona(bot: Bot, event: Event, args: list[str]) -> None:
    if not args:
        await send_to_event(bot, event, _PERSONA_USAGE)
        return
    action, rest = args[0], args[1:]
    scope_key = event_scope_key(bot, event) or ""
    user = str(get_user_id(event) or "")

    if action == "list":
        rows = persona.list_personas()
        if not rows:
            await send_to_event(bot, event, "暂无 persona。")
            return
        lines = [
            f"- {row['name']}：{row['description'] or row['prompt'][:40]}"
            for row in rows
        ]
        await send_to_event(bot, event, "\n".join(lines))
        return

    if action == "show":
        if not rest:
            await send_to_event(bot, event, "用法：ai persona show <name>")
            return
        p = persona.get_persona(rest[0])
        if p is None:
            await send_to_event(bot, event, f"persona `{rest[0]}` 不存在。")
            return
        binds = []
        if scope_key and store.get_scope_persona_id(scope_key) == p["id"]:
            binds.append("当前 scope")
        if store.get_global_value("global_persona") == p["name"]:
            binds.append("全局")
        lines = [f"persona `{p['name']}`", f"prompt：{p['prompt']}"]
        if p["begin_dialogs"]:
            lines.append(f"示例对话：{len(p['begin_dialogs'])} 组")
        if binds:
            lines.append("绑定：" + "、".join(binds))
        await send_to_event(bot, event, "\n".join(lines))
        return

    if action in ("use", "reset"):
        # ADMIN（aicmd matcher 已保证），group/private 均允许（scope 级）。
        if action == "use":
            if not rest:
                await send_to_event(bot, event, "用法：ai persona use <name>")
                return
            if not scope_key:
                await send_to_event(bot, event, "无法解析当前 scope。")
                return
            if persona.bind_scope(scope_key, rest[0], updated_by=user):
                await send_to_event(
                    bot, event, f"已绑定当前会话为 persona `{rest[0]}`。"
                )
            else:
                await send_to_event(bot, event, f"persona `{rest[0]}` 不存在。")
        else:
            if not scope_key:
                await send_to_event(bot, event, "无法解析当前 scope。")
                return
            if persona.clear_scope(scope_key):
                await send_to_event(
                    bot, event, "已解除当前会话的 persona 绑定，回退默认。"
                )
            else:
                await send_to_event(bot, event, "当前会话没有绑定 persona。")
        return

    if action == "global":
        if not _require_superuser(bot, event):
            await send_to_event(bot, event, "仅 SUPERUSER 可设置全局 persona。")
            return
        if not rest:
            await send_to_event(bot, event, "用法：ai persona global <name>|off")
            return
        if rest[0] == "off":
            if persona.clear_global():
                await send_to_event(bot, event, "已清除全局 persona。")
            else:
                await send_to_event(bot, event, "当前没有全局 persona。")
        elif persona.set_global(rest[0]):
            await send_to_event(bot, event, f"已设置全局 persona `{rest[0]}`。")
        else:
            await send_to_event(bot, event, f"persona `{rest[0]}` 不存在。")
        return

    if action == "delete":
        if not _require_superuser(bot, event):
            await send_to_event(bot, event, "仅 SUPERUSER 可删除 persona。")
            return
        if not rest:
            await send_to_event(bot, event, "用法：ai persona delete <name>")
            return
        if persona.delete_persona(rest[0]):
            await send_to_event(bot, event, f"已删除 persona `{rest[0]}`。")
        else:
            await send_to_event(bot, event, f"persona `{rest[0]}` 不存在。")
        return

    await send_to_event(bot, event, _PERSONA_USAGE)
