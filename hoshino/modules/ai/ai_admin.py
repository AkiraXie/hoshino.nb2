"""AI 管理插件：provider / model-list / scope 模型、scope provider 切换、用量查询。

**全部 ``ai`` 管理命令仅超级用户（SUPERUSER）可用**，其他人无法触发（matcher 层
拦截）。命令（平台无关）：
- ``ai setup <id> --url <url> --key <key> [--text <m>] [--vision <m>]``：
  一键配置：新增/更新 provider + 自动注册文本/视觉模型 + 设为全局默认 + 绑定当前群。
- ``ai status``：显示默认 provider、当前绑定与有效模型、历史限制、渲染配置、看图引导。
- ``ai provider list``：列出 provider（url 掩码，不显示 key）。
- ``ai provider default <id>`` / ``use <id>`` / ``reset``：
  设置全局默认 / 绑定当前群 / 清除绑定。
- ``ai provider add/alter/remove <id>``：新增/部分更新/删除 provider。
- ``ai provider model-list <id>`` / ``model-add <id> <m>`` / ``model-remove <id> <m>``。
- ``ai model show`` / ``set text|vision <m>|none`` / ``reset [text|vision]``：
  查看/设置/清除当前群 scope 模型覆盖；未注册的模型会自动注册（text→文本，
  vision→多模态）。
- ``ai stats [provider_id]``：token / 缓存 / 延迟统计（总体 + 按模型明细）。
- ``ai clear [scope]`` / ``ai contexts [scope]``：清空/查看对话。
- ``ai tools list/on/off``、``ai persona ...``：工具类别与人格管理。
"""

from __future__ import annotations

from dataclasses import replace

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
from hoshino.ai.base import get_config, sv
from hoshino.ai.config import mask_url
from hoshino.ai.provider import ProviderRecord

USAGE = (
    "AI 管理（仅超级用户可用）：\n"
    "快速上手：\n"
    "  ai setup <id> --url <url> --key <key> [--text <m>] [--vision <m>]\n"
    "      一键新增 provider + 自动注册模型 + 设为全局默认 + 绑定本群\n"
    "  ai status    查看当前配置与看图引导\n"
    "  ai model set text|vision <模型>   设置本群模型（未注册会自动注册）\n"
    "其他命令：\n"
    "  ai provider list / default <id> / use <id> / reset / add / alter / remove\n"
    "  ai provider model-list <id> / model-add <id> <模型> / model-remove <id> <模型>\n"
    "  ai model show / set text|vision <m>|none / reset [text|vision]\n"
    "  ai stats [provider_id] / clear [scope] / contexts [scope]\n"
    "  ai tools list/on/off / ai persona list/show/create/update/use/reset/global/delete\n"
    "用 ai setup / ai provider add / ai persona create 查看参数说明。"
)

_SETUP_USAGE = (
    "用法：ai setup <provider_id> --url <url> --key <key> [选项]\n"
    "选项：--kind openai_chat|openai_responses|anthropic（默认 openai_chat）\n"
    "      --text <文本模型> --vision <视觉模型>（自动注册进 model-list）\n"
    "      --no-default（不设为全局默认） --no-bind（不绑定当前群）\n"
    "一步完成：新增/更新 provider、注册模型、设为默认并绑定当前群；"
    "之后 ai status 即可看到生效配置。"
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
    "  ai persona create <name> [--gender <g>] [--personality <p>] [--description <d>]\n"
    "             [--dialogs <示例对话文本>]\n"
    "  ai persona update <name> [--gender <g>] [--personality <p>] [--description <d>]\n"
    "             [--dialogs <示例对话文本>]\n"
    "  ai persona use <name>   绑定当前 scope\n"
    "  ai persona reset        解除当前 scope 绑定\n"
    "  ai persona global <name>|off   设置/清除全局\n"
    "  ai persona delete <name>       删除\n"
    "--dialogs 格式：交替的「用户: …」与「<名字>: …」行，作为人格的参考对话风格（few-shot）。"
)

_ADD_USAGE = (
    "用法：ai provider add <id> --url <url> --key <key> [选项]\n"
    "选项：--kind openai_chat|openai_responses|anthropic --model <m> "
    "--vision-model <m> --temperature <t> --max-tokens <n> --timeout <s>\n"
    "model / vision-model 会自动注册进该 provider 的 model-list。"
)

_MODEL_USAGE = (
    "用法：\n"
    "  ai model show\n"
    "  ai model set text <model> | vision <model> | vision none\n"
    "  ai model reset [text|vision]\n"
    "未注册的模型会自动注册（text→文本，vision→多模态），无需先 model-add；\n"
    "vision 的 none 表示显式禁用多模态。\n"
    "示例：ai model set vision gpt-5.6-luna"
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
    """把 ``--key value`` 解析成 dict。

    值缺失（flag 在末尾或后跟另一个 flag）记空串；字面 ``""`` / ``''`` 归一化为
    空串（聊天文本里的空引号），供 alter 等命令表达"清空"。
    """
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
        await send_to_event(bot, event, USAGE)
        return
    action, rest = args[0], args[1:]
    config = get_config()
    if action == "list":
        await _provider_list(bot, event, config)
    elif action == "default":
        await _provider_default(bot, event, rest, config)
    elif action == "use":
        await _provider_use(bot, event, rest)
    elif action == "reset":
        await _provider_reset(bot, event)
    elif action == "add":
        await _provider_add(bot, event, rest)
    elif action == "alter":
        await _provider_alter(bot, event, rest)
    elif action == "remove":
        await _provider_remove(bot, event, rest, config)
    elif action == "model-list":
        await _provider_model_list(bot, event, rest)
    elif action == "model-add":
        await _provider_model_add(bot, event, rest)
    elif action == "model-remove":
        await _provider_model_remove(bot, event, rest)
    else:
        await send_to_event(bot, event, USAGE)


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
    sv.save_config(replace(config, default=pid))
    await send_to_event(bot, event, f"已设置全局默认 provider：`{pid}`")


async def _provider_use(bot: Bot, event: Event, args: list[str]) -> None:
    gid = get_group_id(event)
    if gid is None:
        await send_to_event(bot, event, "私聊不允许切换 provider。")
        return
    if not args:
        await send_to_event(bot, event, "用法：ai provider use <id>")
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


async def _provider_add(bot: Bot, event: Event, args: list[str]) -> None:
    if not _require_superuser(bot, event):
        await send_to_event(bot, event, "仅 SUPERUSER 可新增/修改 provider。")
        return
    if not args:
        await send_to_event(bot, event, _ADD_USAGE)
        return
    pid = args[0]
    opts = _parse_flags(args[1:])
    kind = opts.get("kind", "openai_chat")
    if kind not in provider.KNOWN_KINDS:
        await send_to_event(
            bot, event, "kind 必须是 openai_chat / openai_responses / anthropic。"
        )
        return
    try:
        temperature = float(opts["temperature"]) if opts.get("temperature") else None
        max_tokens = int(opts["max_tokens"]) if opts.get("max_tokens") else None
        timeout_seconds = float(opts["timeout"]) if opts.get("timeout") else None
    except ValueError:
        await send_to_event(
            bot, event, "temperature / max-tokens / timeout 必须是数字。"
        )
        return
    existed = provider.has_provider(pid)
    provider.upsert_provider(
        ProviderRecord(
            id=pid,
            url=opts.get("url", ""),
            key=opts.get("key", ""),
            kind=kind,
            default_text_model=opts.get("model", ""),
            default_vision_model=opts.get("vision_model", ""),
            temperature=temperature,
            max_tokens=max_tokens,
            timeout_seconds=timeout_seconds,
        )
    )
    # 默认模型自动注册进 model-list（已注册的不覆盖其能力标记）。
    if opts.get("model") and store.get_provider_model(pid, opts["model"]) is None:
        store.upsert_provider_model(pid, opts["model"], "text")
    if (
        opts.get("vision_model")
        and store.get_provider_model(pid, opts["vision_model"]) is None
    ):
        store.upsert_provider_model(pid, opts["vision_model"], "multimodal")
    providers.clear_agent_cache()
    verb = "更新" if existed else "新增"
    await send_to_event(bot, event, f"已{verb} provider `{pid}`（kind={kind}）。")


async def _handle_setup(bot: Bot, event: Event, args: list[str]) -> None:
    """一键配置：新增/更新 provider + 自动注册模型 + 设全局默认 + 绑定当前群。"""
    if not _require_superuser(bot, event):
        await send_to_event(bot, event, "仅 SUPERUSER 可配置 provider。")
        return
    if not args:
        await send_to_event(bot, event, _SETUP_USAGE)
        return
    pid = args[0]
    opts = _parse_flags(args[1:])
    kind = opts.get("kind", "openai_chat")
    if kind not in provider.KNOWN_KINDS:
        await send_to_event(
            bot, event, "kind 必须是 openai_chat / openai_responses / anthropic。"
        )
        return
    if not opts.get("url") or not opts.get("key"):
        await send_to_event(bot, event, "setup 需要 --url 与 --key。")
        return

    existed = provider.has_provider(pid)
    provider.upsert_provider(
        ProviderRecord(
            id=pid,
            url=opts.get("url", ""),
            key=opts.get("key", ""),
            kind=kind,
            default_text_model=opts.get("text", ""),
            default_vision_model=opts.get("vision", ""),
        )
    )
    if opts.get("text") and store.get_provider_model(pid, opts["text"]) is None:
        store.upsert_provider_model(pid, opts["text"], "text")
    if opts.get("vision") and store.get_provider_model(pid, opts["vision"]) is None:
        store.upsert_provider_model(pid, opts["vision"], "multimodal")
    providers.clear_agent_cache()

    lines = [f"已{'更新' if existed else '新增'} provider `{pid}`（kind={kind}）。"]
    if "no_default" not in opts:
        sv.save_config(replace(get_config(), default=pid))
        lines.append("已设为全局默认 provider。")
    gid = get_group_id(event)
    if gid is not None and "no_bind" not in opts:
        scope_key = group_scope_key(gid, platform=platform_key(bot))
        store.set_scope_provider(
            scope_key, pid, updated_by=str(get_user_id(event) or "")
        )
        lines.append("已绑定当前群。")
    if opts.get("text"):
        lines.append(f"文本模型：`{opts['text']}`（已注册）。")
    if opts.get("vision"):
        lines.append(f"视觉模型：`{opts['vision']}`（已注册为 multimodal，可看图）。")
    else:
        lines.append(
            "视觉模型未设置：看图需配置 vision 模型，可 `ai model set vision <模型>`（自动注册）。"
        )
    lines.append("用 `ai status` 查看生效配置。")
    await send_to_event(bot, event, "\n".join(lines))


_ALTER_USAGE = (
    "用法：ai provider alter <id> [--url <u>] [--key <k>] [--kind <kind>] "
    "[--model <m>] [--vision-model <m>] [--temperature <t>] [--max-tokens <n>] "
    "[--timeout <s>]\n"
    "只变更显式传入的属性，其余保持不变；传空值表示清空该项。"
)


async def _provider_alter(bot: Bot, event: Event, args: list[str]) -> None:
    """部分更新 provider 属性：未显式传入的字段保持原值，空值清空。"""
    if not _require_superuser(bot, event):
        await send_to_event(bot, event, "仅 SUPERUSER 可变更 provider。")
        return
    if not args:
        await send_to_event(bot, event, _ALTER_USAGE)
        return
    pid = args[0]
    record = provider.get_provider(pid)
    if record is None:
        await send_to_event(bot, event, f"provider `{pid}` 不存在。")
        return
    opts = _parse_flags(args[1:])
    kind = opts["kind"] if "kind" in opts else record.kind
    if kind not in provider.KNOWN_KINDS:
        await send_to_event(
            bot, event, "kind 必须是 openai_chat / openai_responses / anthropic。"
        )
        return
    try:
        if "temperature" in opts:
            temperature = float(opts["temperature"]) if opts["temperature"] else None
        else:
            temperature = record.temperature
        if "max_tokens" in opts:
            max_tokens = int(opts["max_tokens"]) if opts["max_tokens"] else None
        else:
            max_tokens = record.max_tokens
        if "timeout" in opts:
            timeout_seconds = float(opts["timeout"]) if opts["timeout"] else None
        else:
            timeout_seconds = record.timeout_seconds
    except ValueError:
        await send_to_event(
            bot, event, "temperature / max-tokens / timeout 必须是数字。"
        )
        return
    provider.upsert_provider(
        ProviderRecord(
            id=pid,
            url=opts["url"] if "url" in opts else record.url,
            key=opts["key"] if "key" in opts else record.key,
            kind=kind,
            default_text_model=(
                opts["model"] if "model" in opts else record.default_text_model
            ),
            default_vision_model=(
                opts["vision_model"]
                if "vision_model" in opts
                else record.default_vision_model
            ),
            temperature=temperature,
            max_tokens=max_tokens,
            timeout_seconds=timeout_seconds,
        )
    )
    # 变更的默认模型自动注册进 model-list（已注册的不覆盖其能力标记）。
    if opts.get("model") and store.get_provider_model(pid, opts["model"]) is None:
        store.upsert_provider_model(pid, opts["model"], "text")
    if (
        opts.get("vision_model")
        and store.get_provider_model(pid, opts["vision_model"]) is None
    ):
        store.upsert_provider_model(pid, opts["vision_model"], "multimodal")
    providers.clear_agent_cache()
    await send_to_event(bot, event, f"已变更 provider `{pid}` 的属性（kind={kind}）。")


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


# ------------------------------------------------------------ model-list


async def _provider_model_list(bot: Bot, event: Event, args: list[str]) -> None:
    if not args:
        await send_to_event(bot, event, "用法：ai provider model-list <id>")
        return
    pid = args[0]
    if not provider.has_provider(pid):
        await send_to_event(bot, event, f"provider `{pid}` 不存在。")
        return
    models = provider.list_models(pid)
    if not models:
        await send_to_event(bot, event, f"provider `{pid}` 还没有注册任何模型。")
        return
    lines = [f"provider `{pid}` 的 model-list："]
    for entry in models:
        lines.append(f"- `{entry['model']}` [{entry['capabilities']}]")
    await send_to_event(bot, event, "\n".join(lines))


async def _provider_model_add(bot: Bot, event: Event, args: list[str]) -> None:
    if not _require_superuser(bot, event):
        await send_to_event(bot, event, "仅 SUPERUSER 可修改 model-list。")
        return
    if not args or len(args) < 2:
        await send_to_event(
            bot,
            event,
            "用法：ai provider model-add <id> <model> [--capabilities text|multimodal|both]",
        )
        return
    pid, model = args[0], args[1]
    opts = _parse_flags(args[2:])
    capabilities = opts.get("capabilities", "text")
    if capabilities not in ("text", "multimodal", "both"):
        await send_to_event(
            bot, event, "capabilities 必须是 text / multimodal / both。"
        )
        return
    if not provider.has_provider(pid):
        await send_to_event(bot, event, f"provider `{pid}` 不存在。")
        return
    provider.add_model(pid, model, capabilities)
    await send_to_event(
        bot, event, f"已注册模型 `{model}`（{capabilities}）到 `{pid}`。"
    )


async def _provider_model_remove(bot: Bot, event: Event, args: list[str]) -> None:
    if not _require_superuser(bot, event):
        await send_to_event(bot, event, "仅 SUPERUSER 可修改 model-list。")
        return
    if not args or len(args) < 2:
        await send_to_event(bot, event, "用法：ai provider model-remove <id> <model>")
        return
    pid, model = args[0], args[1]
    record = provider.get_provider(pid)
    if record is None:
        await send_to_event(bot, event, f"provider `{pid}` 不存在。")
        return
    if model in (record.default_text_model, record.default_vision_model):
        await send_to_event(
            bot,
            event,
            f"模型 `{model}` 是 `{pid}` 的默认模型，请先修改 provider 再删除。",
        )
        return
    if provider.remove_model(pid, model):
        await send_to_event(bot, event, f"已从 `{pid}` 移除模型 `{model}`。")
    else:
        await send_to_event(
            bot, event, f"模型 `{model}` 不在 `{pid}` 的 model-list 中。"
        )


# ------------------------------------------------------------ scope models


async def _handle_model(bot: Bot, event: Event, args: list[str]) -> None:
    if not args:
        await send_to_event(bot, event, _MODEL_USAGE)
        return
    action, rest = args[0], args[1:]
    if action == "show":
        await _model_show(bot, event)
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
        await send_to_event(bot, event, _MODEL_USAGE)


async def _scope_provider_id(scope_key: str, config) -> str | None:
    """当前 scope 的有效 provider id（scope 绑定 > 默认），不存在返回 None。"""
    bound = store.get_scope_provider(scope_key)
    if bound and provider.has_provider(bound):
        return bound
    if config.default and provider.has_provider(config.default):
        return config.default
    return None


async def _model_show(bot: Bot, event: Event) -> None:
    config = get_config()
    scope_key = event_scope_key(bot, event)
    bound = store.get_scope_provider(scope_key) if scope_key else None
    pid = await _scope_provider_id(scope_key, config) if scope_key else None
    if pid is None:
        await send_to_event(bot, event, "当前会话没有可用 provider，无法解析模型。")
        return
    text_model, vision_model = provider.resolve_models(scope_key, pid)
    overrides = store.get_scope_model_overrides(scope_key or "")
    source_text = "覆盖" if overrides["text_model"] else "默认"
    source_vision = (
        "覆盖"
        if overrides["vision_model"]
        else (
            "显式禁用"
            if overrides["vision_model"] == provider.VISION_DISABLED
            else "默认"
        )
    )
    lines = [
        f"provider：`{pid}`" + ("" if not bound else "（本群绑定）"),
        f"纯文本模型：`{text_model or '（未配置）'}`（{source_text}）",
        f"多模态模型：`{vision_model or '（无）'}`（{source_vision}）",
    ]
    models = provider.list_models(pid)
    if models:
        cap = {"text": "文本", "multimodal": "多模态", "both": "文本+多模态"}
        lines.append(
            "可用模型："
            + "；".join(
                f"`{m['model']}`（{cap.get(m['capabilities'], m['capabilities'])}）"
                for m in models
            )
        )
    if not vision_model:
        lines.append("提示：看图需先注册多模态模型，见 `ai model` 用法说明。")
    await send_to_event(bot, event, "\n".join(lines))


async def _model_set(bot: Bot, event: Event, scope_key: str, args: list[str]) -> None:
    if len(args) != 2 or args[0] not in ("text", "vision"):
        await send_to_event(bot, event, "用法：ai model set text|vision <model>")
        return
    slot, model = args[0], args[1]
    config = get_config()
    pid = await _scope_provider_id(scope_key, config)
    if pid is None:
        await send_to_event(
            bot, event, "本群没有可用 provider，请先 `ai provider use <id>`。"
        )
        return
    # 未注册的模型自动注册（text→文本 / vision→多模态），省去手动 model-add。
    existing = store.get_provider_model(pid, model)
    if existing is None:
        capability = "multimodal" if slot == "vision" else "text"
        store.upsert_provider_model(pid, model, capability)
        providers.clear_agent_cache()
    error = provider.validate_model_choice(pid, model, slot)
    if error:
        # 已注册但能力不匹配（如把纯文本模型设为 vision）
        models = provider.list_models(pid)
        hint = ""
        if models:
            cap = {"text": "文本", "multimodal": "多模态", "both": "文本+多模态"}
            hint = "\n当前 provider 可用模型：\n" + "\n".join(
                f"- `{m['model']}`（{cap.get(m['capabilities'], m['capabilities'])}）"
                for m in models
            )
        await send_to_event(bot, event, error + hint)
        return
    store.set_scope_model_override(
        scope_key, slot, model, updated_by=str(get_user_id(event) or "")
    )
    label = "纯文本" if slot == "text" else "多模态"
    display = "none（禁用）" if model == provider.VISION_DISABLED else f"`{model}`"
    registered = "" if existing is not None else "（已自动注册）"
    await send_to_event(bot, event, f"本群{label}模型已设为 {display}{registered}。")


async def _model_reset(bot: Bot, event: Event, scope_key: str, args: list[str]) -> None:
    if args and args[0] not in ("text", "vision"):
        await send_to_event(bot, event, "用法：ai model reset [text|vision]")
        return
    slot = args[0] if args else None
    if store.clear_scope_model_override(scope_key, slot):
        label = (
            "纯文本模型"
            if slot == "text"
            else ("多模态模型" if slot == "vision" else "模型")
        )
        await send_to_event(bot, event, f"已清除本群{label}覆盖，回退 provider 默认。")
    else:
        await send_to_event(
            bot, event, "本群当前没有模型覆盖。" if slot is None else "该槽位没有覆盖。"
        )


async def _handle_status(bot: Bot, event: Event) -> None:
    config = get_config()
    scope_key = event_scope_key(bot, event)
    bound = store.get_scope_provider(scope_key) if scope_key else None
    provider_id = bound or config.default
    record = provider.get_provider(provider_id) if provider_id else None
    # 原生联网搜索只在 anthropic / openai_responses kind 上生效（服务端 web_search）。
    native_search = (
        config.web_search_native
        and record is not None
        and record.kind in ("anthropic", "openai_responses")
    )
    text_model, vision_model = (
        provider.resolve_models(scope_key, provider_id)
        if scope_key and provider_id
        else ("", "")
    )
    lines = [
        f"默认 provider：`{config.default}`"
        if config.default
        else "默认 provider：未设置",
        f"当前 scope 绑定：`{bound}`" if bound else "当前 scope 绑定：无（回退默认）",
        f"纯文本模型：`{text_model or '（未配置）'}`",
        f"多模态模型：`{vision_model or '（无）'}`",
        f"历史长度限制：{config.max_history_messages} 条",
        f"渲染超时：{config.render_timeout_seconds}s",
        f"渲染主题：{config.render_theme}",
        f"渲染字体：{config.render_font}",
        f"代理：{config.proxy or '未设置'}",
        f"原生联网搜索：{'开（服务端 web_search）' if native_search else '关'}"
        f"（工具重试预算 {config.tool_max_retries} 次）",
        f"provider 数量：{len(provider.list_providers())}",
    ]
    if vision_model:
        lines.append(f"看图：已启用（vision 模型 `{vision_model}`）")
    else:
        lines.extend(
            [
                "看图：未启用",
                "配置多模态（看图）三步：",
                "1. 注册多模态模型：`ai provider model-add <id> <模型> --capabilities multimodal`（可用模型见 `ai provider model-list <id>`）",
                "2. 确认本群用该 provider：`ai provider use <id>`",
                "3. 设置视觉模型：`ai model set vision <模型>`（或让超级用户用 provider-choose 工具直接调）",
            ]
        )
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


def _parse_persona_args(args: list[str]) -> dict[str, str]:
    """解析 ``--key value``（value 可含空格，直到下一个 -- 或末尾）。"""
    opts: dict[str, list[str]] = {}
    current: str | None = None
    for token in args:
        if token.startswith("--"):
            current = token[2:].replace("-", "_")
            opts[current] = []
        elif current is not None:
            opts[current].append(token)
    return {k: " ".join(v).strip() for k, v in opts.items() if v}


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

    if action == "create":
        if not rest:
            await send_to_event(
                bot,
                event,
                "用法：ai persona create <name> [--gender ...] [--personality ...] [--description ...]",
            )
            return
        name = rest[0]
        opts = _parse_persona_args(rest[1:])
        dialogs = (
            persona.parse_dialogs_text(opts["dialogs"], name)
            if opts.get("dialogs")
            else None
        )
        try:
            p = persona.create_persona(
                name,
                gender=opts.get("gender", ""),
                personality=opts.get("personality", ""),
                description=opts.get("description", ""),
                begin_dialogs=dialogs,
                created_by=user,
            )
        except ValueError as exc:
            await send_to_event(bot, event, str(exc))
            return
        reply = f"已创建 persona `{p['name']}`：{p['prompt']}"
        if dialogs:
            reply += f"\n示例对话 {len(dialogs)} 组。"
        await send_to_event(bot, event, reply)
        return

    if action == "update":
        if not rest:
            await send_to_event(
                bot,
                event,
                "用法：ai persona update <name> [--gender ...] [--personality ...] [--description ...]",
            )
            return
        name = rest[0]
        opts = _parse_persona_args(rest[1:])
        dialogs = (
            persona.parse_dialogs_text(opts["dialogs"], name)
            if opts.get("dialogs")
            else None
        )
        p = persona.update_persona(
            name,
            gender=opts.get("gender"),
            personality=opts.get("personality"),
            description=opts.get("description"),
            begin_dialogs=dialogs,
        )
        if p is None:
            await send_to_event(bot, event, f"persona `{name}` 不存在。")
            return
        reply = f"已更新 persona `{p['name']}`：{p['prompt']}"
        if dialogs:
            reply += f"\n示例对话 {len(dialogs)} 组。"
        await send_to_event(bot, event, reply)
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
