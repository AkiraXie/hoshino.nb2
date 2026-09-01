"""AI 管理插件：provider / model / scope 配置与用量查询（**仅超级用户可用**）。

模型管理语义（唯一槽）：
- ``ai model``：显示当前生效 model（含来源）。
- ``ai model list``：列出所有 provider 的可用模型，并标注当前 model。
- ``ai model set <provider> <模型>`` / ``<provider>/<模型>``：本群覆盖。
- ``ai model reset``：清除本群覆盖，回退全局默认。
- ``ai model default <provider> <模型>``：全局默认（仅 SUPERUSER）；``none`` 清除。

搜索管理语义（独立搜索 provider，与聊天 provider 解耦，默认 deepseek；
支持配置多个 provider，再选一个作为默认生效）：
- ``ai search``：显示当前生效的搜索 provider（kind/端点/模型；key 只显示已配置/未设置）。
- ``ai search add <名字> <kind> [--url <u>] [--key <k>] [--model <m>]``：
  添加/更新搜索 provider。deepseek 省略项回退 DEFAULT 端点/模型，key 可借聊天
  provider；tavily/bocha 只需要 --key。
- ``ai search default <名字>``（``set`` 同义）：把某个 provider 设为默认生效。
- ``ai search list``：列出所有已配置的 provider（默认标记）。
- ``ai search remove <名字>``：删除一个 provider。
- ``ai config`` 仅代理/渲染语义，不涉及搜索；搜索走 ``ai search``。

provider 管理语义（全局资源，不与群绑定）：
- ``ai provider [list]``：列出已配置的 provider（只读）。
- ``ai setup <id> --url <url> --key <key>``：新增/更新 provider + 设为全局默认。
- ``ai alter <id> [--url/--key/--use-proxy]``：按需修改已有 provider 的个别字段。
- ``ai provider remove <id>``：删除 provider。

裸 ``ai`` / ``ai status`` 只显示 model + 搜索状态。

其余：``ai stats [provider_id]``、``ai clear [scope]``、
``ai contexts [scope]``、``ai tools ...``、``ai persona ...``。
"""

from __future__ import annotations

from nonebot.adapters import Bot, Event
from nonebot_plugin_alconna.uniseg import Target

from hoshino.ai import (
    deps,
    metrics,
    persona,
    provider,
    providers,
    search,
    sessions,
    store,
    tools,
)
from hoshino.ai.base import get_config
from hoshino.ai.config import mask_url, write_ai_config_env
from hoshino.ai.provider import ProviderRecord
from hoshino.core.permission import SUPERUSER
from hoshino.core.service import Service
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

# ai_admin 服务：管理命令（ai / ai task）统一挂此服务，默认开启（仅 SUPERUSER 可用）。
sv = Service("ai_admin", enable_on_default=True, visible=False)

USAGE = (
    "AI 管理（仅超级用户可用）：\n"
    "Provider 管理：\n"
    "  ai setup <id> --url <u> --key <k>  新增/更新 provider\n"
    "  ai alter <id> [--url/--key/--use-proxy]  按需修改已有 provider\n"
    "  ai provider [list]                 查看已配置的 provider\n"
    "  ai provider remove <id>            删除 provider\n"
    "模型管理：\n"
    "  ai model              查看当前生效 model\n"
    "  ai model list         列出所有 provider 的可用模型\n"
    "  ai model set|reset|default\n"
    "搜索：\n"
    "  ai search             查看/管理搜索 provider\n"
    "其他：\n"
    "  ai search list / add <名字> <kind> / default|set <名字> / remove\n"
    "  ai status / ai stats [provider_id]\n"
    "  ai clear [scope] / ai contexts [scope] / ai tools ... / ai persona ...\n"
    "  ai config [set <key> <value> | reset <key>]  在线改代理/渲染参数并写盘\n"
    "  ai task research|plan|status|list|approve|deny|cancel|workspaces\n"
    "用 ai setup / ai model / ai search / ai config 查看参数说明。"
)

_SETUP_USAGE = (
    "用法：ai setup <provider_id> --url <url> --key <key>\n"
    "  [--use-proxy [1|0]]   走全局代理 OUTSIDE_PROXY（默认保持原值，显式 0 关闭）\n"
    "一步完成：新增/更新 provider（openai_chat 兼容）、设为全局默认；\n"
    "默认模型请用 `ai model default <provider> <模型>` 单独配置。"
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
    "  ai model                             查看当前生效 model（含来源）\n"
    "  ai model list                        列出所有 provider 的可用模型\n"
    "  ai model set <provider> <模型>        设置本群 model\n"
    "  ai model set <provider>/<模型>        同上（斜杠分隔）\n"
    "  ai model reset                        清除本群覆盖，回退全局默认\n"
    "  ai model default <provider> <模型>    设置全局默认（仅 SUPERUSER）\n"
    "  ai model default none                 清除全局默认\n"
    "示例：ai model set my-openai gpt-4o；ai model default my-openai/gpt-4o"
)

_SEARCH_USAGE = (
    "用法：\n"
    "  ai search                           查看当前生效的搜索 provider\n"
    "  ai search list                      列出所有已配置的搜索 provider\n"
    "  ai search add <名字> <kind> [--url <u>] [--key <k>] [--model <m>]\n"
    "                                       添加/更新搜索 provider（名字自定）\n"
    "  ai search default <名字>            把某个 provider 设为默认生效\n"
    "  ai search set <名字>                （同 default）\n"
    "  ai search remove <名字>             删除一个 provider\n"
    "kind 可选：deepseek / tavily / bocha。deepseek 省略 --url/--key/--model 时\n"
    "回退默认端点/模型，key 可借自当前聊天 provider（任意 kind）；tavily/bocha 只需\n"
    "--key（端点与模型已内置）。key 只写入 DB，命令输出不显示。"
)

# ai config 可在线修改并写盘的白名单：仅代理与渲染相关参数。
CONFIG_EDITABLE = (
    "proxy",
    "render_font",
    "render_theme",
    "render_timeout_seconds",
    "render_device_scale",
    "render_emoji",
)
# 写盘目标（.env.prod；测试可 monkeypatch 到临时文件）。
AI_ENV_FILE = ".env.prod"

_CONFIG_USAGE = (
    "用法：\n"
    "  ai config                   查看当前代理/渲染配置\n"
    "  ai config set <key> <value> 修改并写盘（.env.prod）\n"
    "  ai config reset <key>       删除对应行，恢复代码默认\n"
    "可改参数（仅代理与渲染相关）：\n"
    "  proxy <http(s)://|socks://...>   代理（清空用 reset）\n"
    "  render_font <字体名>             渲染主字体\n"
    "  render_theme light|dark          渲染主题\n"
    "  render_timeout_seconds <秒>      渲染超时\n"
    "  render_device_scale <倍数>       渲染清晰度（2.0=2x）\n"
    "  render_emoji true|false          渲染是否启用彩色 emoji\n"
    "其余 AI 配置项不支持在线修改，请直接编辑 .env.prod。"
)

# 全部 ai 管理命令仅 SUPERUSER 可用；only_group=False 让私聊也能触发，从而在
# handler 内给出“私聊不允许”的明确提示，而不是静默无响应。
aicmd = sv.on_command("ai", permission=SUPERUSER, compact=False, only_group=False)


@aicmd.handle()
async def _(bot: Bot, event: Event, text: str = ParamText()):
    args = text.strip().split()
    if not args:
        # 裸 `ai`：直接给状态总览，比命令清单更自然。
        await _handle_status(bot, event)
        return
    sub, rest = args[0], args[1:]
    match sub:
        case "help" | "?":
            await send_to_event(bot, event, USAGE)
        case "setup":
            await _handle_setup(bot, event, rest)
        case "alter":
            await _handle_alter(bot, event, rest)
        case "provider":
            await _handle_provider(bot, event, rest)
        case "model":
            await _handle_model(bot, event, rest)
        case "search":
            await _handle_search(bot, event, rest)
        case "status":
            await _handle_status(bot, event)
        case "stats":
            await _handle_stats(bot, event, rest)
        case "clear":
            await _handle_clear(bot, event, rest)
        case "contexts":
            await _handle_contexts(bot, event, rest)
        case "tools":
            await _handle_tools(bot, event, rest)
        case "persona":
            await _handle_persona(bot, event, rest)
        case "config":
            await _handle_config(bot, event, rest)
        case _:
            # 未识别的子命令静默忽略，避免 "ai 是什么" / "ai workflow" 等日常对话误触发。
            return


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
        await _provider_list(bot, event)
        return
    action, rest = args[0], args[1:]
    match action:
        case "list":
            await _provider_list(bot, event)
        case "remove":
            await _provider_remove(bot, event, rest)
        case _:
            await send_to_event(bot, event, "用法：ai provider [list] / ai provider remove <id>")


async def _provider_list(bot: Bot, event: Event) -> None:
    records = provider.list_providers()
    if not records:
        await send_to_event(bot, event, "未配置任何 provider。新增请用 `ai setup`。")
        return
    lines = ["已配置的 provider："]
    for record in records:
        proxy_flag = " proxy=on" if record.use_proxy else ""
        lines.append(f"- `{record.id}` kind={record.kind} url={mask_url(record.url)}{proxy_flag}")
    await send_to_event(bot, event, "\n".join(lines))


async def _handle_setup(bot: Bot, event: Event, args: list[str]) -> None:
    """一键配置：新增/更新 provider + 设全局默认。"""
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

    old = provider.get_provider(pid)
    use_proxy = old.use_proxy if old is not None else False
    if "use_proxy" in opts:
        use_proxy = opts["use_proxy"].lower() not in ("0", "false", "no", "off")
    provider.upsert_provider(
        ProviderRecord(
            id=pid,
            url=opts.get("url", ""),
            key=opts.get("key", ""),
            kind="openai_chat",
            use_proxy=use_proxy,
        )
    )
    providers.clear_agent_cache()

    store.set_global_value("default_provider", pid)
    parts = [f"已{'更新' if old is not None else '新增'} `{pid}`"]
    parts.append(f"proxy={'on' if use_proxy else 'off'}")
    await send_to_event(bot, event, "、".join(parts))


_ALTER_USAGE = (
    "用法：ai alter <id> [--url <u>] [--key <k>] [--kind <k>] "
    "[--use-proxy [1|0]]\n"
    "按需修改已有 provider 的字段，只提供要改的项；未提供的保持不变。\n"
    "  --url          API 地址\n"
    "  --key          API Key\n"
    "  --kind         协议格式：openai_chat / openai_responses / anthropic\n"
    "  --use-proxy 1  走全局代理（AI_PROXY / OUTSIDE_PROXY）\n"
    "  --use-proxy 0  关闭代理，直连"
)


async def _handle_alter(bot: Bot, event: Event, args: list[str]) -> None:
    """按需修改已有 provider 的个别字段（不要求全量提供）。"""
    if not _require_superuser(bot, event):
        await send_to_event(bot, event, "仅 SUPERUSER 可修改 provider。")
        return
    if not args:
        await send_to_event(bot, event, _ALTER_USAGE)
        return
    pid = args[0]
    old = provider.get_provider(pid)
    if old is None:
        await send_to_event(bot, event, f"provider `{pid}` 不存在，新增请用 `ai setup`。")
        return
    opts = _parse_flags(args[1:])
    if not opts:
        await send_to_event(bot, event, _ALTER_USAGE)
        return

    url = opts.get("url", old.url)
    key = opts.get("key", old.key)
    kind = old.kind
    if "kind" in opts:
        if opts["kind"] not in provider.KNOWN_KINDS:
            await send_to_event(
                bot,
                event,
                f"不支持的 kind `{opts['kind']}`：可选 " + " / ".join(provider.KNOWN_KINDS),
            )
            return
        kind = opts["kind"]
    use_proxy = old.use_proxy
    if "use_proxy" in opts:
        use_proxy = opts["use_proxy"].lower() not in ("0", "false", "no", "off")

    updated = ProviderRecord(
        id=pid,
        url=url,
        key=key,
        kind=kind,
        use_proxy=use_proxy,
        timeout_seconds=old.timeout_seconds,
    )
    provider.upsert_provider(updated)
    providers.clear_agent_cache()

    changes: list[str] = []
    if "url" in opts:
        changes.append(f"url={mask_url(url)}")
    if "kind" in opts:
        changes.append(f"kind={kind}")
    if "key" in opts:
        changes.append("key=***（已更新）")
    if "use_proxy" in opts:
        changes.append(f"use_proxy={'on' if use_proxy else 'off'}")
    summary = "、".join(changes) if changes else "无变化"
    await send_to_event(bot, event, f"已更新 provider `{pid}`：{summary}")


async def _provider_remove(bot: Bot, event: Event, args: list[str]) -> None:
    if not _require_superuser(bot, event):
        await send_to_event(bot, event, "仅 SUPERUSER 可删除 provider。")
        return
    if not args:
        await send_to_event(bot, event, "用法：ai provider remove <id>")
        return
    pid = args[0]
    if not provider.has_provider(pid):
        await send_to_event(bot, event, f"provider `{pid}` 不存在。")
        return
    provider.remove_provider(pid)
    providers.clear_agent_cache()
    await send_to_event(bot, event, f"已删除 provider `{pid}`。")


# ------------------------------------------------------------ scope models


def _parse_provider_model(args: list[str]) -> tuple[str, str] | None:
    """解析 ``<provider> <model>`` 或 ``<provider>/<model>`` 为 (provider, model)。

    斜杠形式按第一个 ``/`` 切分（模型名可含 ``/``，如 ``org/model``）。
    """
    if len(args) == 1:
        spec = args[0]
        if "/" in spec:
            pid, _, model = spec.partition("/")
            return (pid, model) if pid and model else None
        return None
    if len(args) == 2:
        return (args[0], args[1]) if args[0] and args[1] else None
    return None


async def _handle_model(bot: Bot, event: Event, args: list[str]) -> None:
    """``ai model``：查看/设置统一 model 槽。"""
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
    if action == "default":
        await _model_default(bot, event, rest)
        return
    gid = get_group_id(event)
    if gid is None:
        await send_to_event(bot, event, "model 设置仅限群聊。")
        return
    scope_key = group_scope_key(gid, platform=platform_key(bot))
    if action == "set":
        await _model_set(bot, event, scope_key, rest)
    elif action == "reset":
        await _model_reset(bot, event, scope_key, rest)
    else:
        await send_to_event(bot, event, _MODEL_USAGE)


def _model_source(scope_key: str | None) -> str:
    overrides = store.get_scope_model_overrides(scope_key or "")
    if overrides["provider"] and overrides["model"]:
        return "本群覆盖"
    if store.get_global_value(provider.MODEL_GLOBAL_PROVIDER):
        return "全局默认"
    return "未配置"


async def _model_status(bot: Bot, event: Event) -> None:
    """`ai model`：当前生效 model（含来源）。"""
    scope_key = event_scope_key(bot, event)
    model_pid, model = provider.resolve_model(scope_key)
    source = _model_source(scope_key)
    current = f"`{model_pid}` / `{model}`" if model_pid and model else "`（未设置）`"
    await send_to_event(bot, event, f"model：{current}（{source}）")


async def _echo_model(bot: Bot, event: Event, scope_key: str, extra: str = "") -> None:
    model_pid, model = provider.resolve_model(scope_key)
    current = f"`{model_pid}` / `{model}`" if model_pid and model else "`（未设置）`"
    await send_to_event(bot, event, f"model：{current}{extra}")


async def _model_list(bot: Bot, event: Event) -> None:
    """`ai model list`：列出所有 provider 的可用模型，并标注当前 model。"""
    config = get_config()
    scope_key = event_scope_key(bot, event)
    records = provider.list_providers()
    if not records:
        await send_to_event(bot, event, "未配置任何 provider，无法获取模型列表。")
        return

    model_pid, model_name = provider.resolve_model(scope_key)

    sections: list[str] = []
    for record in records:
        models = await provider.fetch_available_models(
            record,
            proxy=provider.resolve_effective_proxy(record, config.proxy),
            verify=config.web_fetch_verify_ssl,
        )
        if models is None:
            sections.append(f"`{record.id}`：获取失败（网络或端点不支持）")
            continue
        header = f"`{record.id}`（{len(models)} 个模型）："
        lines = [header]
        for model in models:
            mark = "  ← 当前" if record.id == model_pid and model == model_name else ""
            lines.append(f"- {model}{mark}")
        sections.append("\n".join(lines))

    await send_to_event(bot, event, "\n\n".join(sections))


async def _model_set(bot: Bot, event: Event, scope_key: str, args: list[str]) -> None:
    """`ai model set <provider> <模型>` / `<provider>/<模型>`。"""
    actor = str(get_user_id(event) or "")
    if not args:
        await send_to_event(bot, event, _MODEL_USAGE)
        return
    spec = _parse_provider_model(args)
    if spec is None:
        await send_to_event(
            bot, event, "用法：ai model set <provider> <模型>（或 <provider>/<模型>）"
        )
        return
    pid, model = spec
    if not provider.has_provider(pid):
        await send_to_event(bot, event, f"provider `{pid}` 不存在。")
        return

    config = get_config()
    record = provider.get_provider(pid)
    available = await provider.fetch_available_models(
        record,
        proxy=provider.resolve_effective_proxy(record, config.proxy),
        verify=config.web_fetch_verify_ssl,
    )
    warning = ""
    if available is not None:
        if model not in available:
            await send_to_event(
                bot, event, f"`{model}` 不在 `{pid}` 可用列表中，用 `ai model list` 查看。"
            )
            return
    else:
        warning = "（未校验）"

    store.set_scope_model(scope_key, pid, model, updated_by=actor)
    await _echo_model(bot, event, scope_key, warning)


async def _model_reset(bot: Bot, event: Event, scope_key: str, args: list[str]) -> None:
    """`ai model reset`：清除本群 model 覆盖，回退全局默认。"""
    if args:
        await send_to_event(bot, event, "用法：ai model reset")
        return
    cleared = store.clear_scope_model(scope_key)
    if not cleared:
        await send_to_event(bot, event, "本群当前没有 model 覆盖。")
        return
    await _echo_model(bot, event, scope_key, "（已清除本群覆盖）")


async def _model_default(bot: Bot, event: Event, args: list[str]) -> None:
    """`ai model default <provider> <模型>`：设置全局默认 model（仅 SUPERUSER）。"""
    if not _require_superuser(bot, event):
        await send_to_event(bot, event, "仅 SUPERUSER 可设置全局默认 model。")
        return
    if not args:
        await send_to_event(bot, event, "用法：ai model default <provider> <模型>|none")
        return
    if args[0] == "none":
        if len(args) != 1:
            await send_to_event(bot, event, "用法：ai model default none")
            return
        store.clear_global_value(provider.MODEL_GLOBAL_PROVIDER)
        store.clear_global_value(provider.MODEL_GLOBAL_MODEL)
        await send_to_event(bot, event, "已清除全局默认 model。")
        return
    spec = _parse_provider_model(args)
    if spec is None:
        await send_to_event(
            bot, event, "用法：ai model default <provider> <模型>（或 <provider>/<模型>）"
        )
        return
    pid, model = spec
    if not provider.has_provider(pid):
        await send_to_event(bot, event, f"provider `{pid}` 不存在。")
        return

    config = get_config()
    record = provider.get_provider(pid)
    available = await provider.fetch_available_models(
        record,
        proxy=provider.resolve_effective_proxy(record, config.proxy),
        verify=config.web_fetch_verify_ssl,
    )
    warning = ""
    if available is not None:
        if model not in available:
            await send_to_event(bot, event, f"`{model}` 不在 `{pid}` 可用列表中。")
            return
    else:
        warning = "（未校验）"
    store.set_global_value(provider.MODEL_GLOBAL_PROVIDER, pid)
    store.set_global_value(provider.MODEL_GLOBAL_MODEL, model)
    await send_to_event(bot, event, f"全局 model 默认：`{pid}` / `{model}`{warning}")


async def _handle_status(bot: Bot, event: Event) -> None:
    """``ai`` / ``ai status``：model + 搜索状态总览。"""
    config = get_config()
    scope_key = event_scope_key(bot, event)

    model_pid, model = provider.resolve_model(scope_key)
    model_line = (
        f"model：`{model_pid}` / `{model}`" if model_pid and model else "model：`（未设置）`"
    )

    search_cfg = search.resolve_search_config(scope_key, config)
    if search_cfg is not None:
        default_id = store.get_search_default_id()
        search_label = (
            f"`{default_id}`（`{search_cfg.kind}`）" if default_id else f"`{search_cfg.kind}`"
        )
        search_line = f"search：{search_label}"
    else:
        search_line = "search：`（未配置）`"

    await send_to_event(bot, event, f"{model_line}\n{search_line}")


# ------------------------------------------------------------ search


async def _handle_search(bot: Bot, event: Event, args: list[str]) -> None:
    """``ai search``：查看/管理搜索 provider（多 provider，选默认生效）。"""
    if not args:
        await _search_status(bot, event)
        return
    action, rest = args[0], args[1:]
    if action in ("show", "status"):
        await _search_status(bot, event)
    elif action == "list":
        await _search_list(bot, event)
    elif action == "add":
        await _search_add(bot, event, rest)
    elif action in ("default", "set"):
        await _search_set_default(bot, event, rest)
    elif action in ("remove", "del"):
        await _search_remove(bot, event, rest)
    else:
        await send_to_event(bot, event, _SEARCH_USAGE)


async def _search_status(bot: Bot, event: Event) -> None:
    """`ai search`：当前生效的搜索 provider（kind/端点/模型，key 脱敏）+ 来源。"""
    config = get_config()
    scope_key = event_scope_key(bot, event)
    default_id = store.get_search_default_id()
    cfg = search.resolve_search_config(scope_key, config)
    if cfg is None:
        await send_to_event(bot, event, "搜索未配置。")
        return
    source = "自定义" if default_id else "默认"
    label = f"`{default_id}`（`{cfg.kind}`）" if default_id else f"`{cfg.kind}`"
    lines = [f"搜索：{label}（{source}）", f"端点：{mask_url(cfg.url)}"]
    if cfg.kind == "deepseek":
        lines.append(f"模型：`{cfg.model}`")
    await send_to_event(bot, event, "\n".join(lines))


async def _search_list(bot: Bot, event: Event) -> None:
    """`ai search list`：列出所有已配置的搜索 provider（默认标记）。"""
    rows = store.list_search_providers()
    if not rows:
        await send_to_event(
            bot,
            event,
            "还没有配置搜索 provider：`ai search add <名字> <deepseek|tavily|bocha> [--key <k>]`。",
        )
        return
    default_id = store.get_search_default_id()
    lines = [f"已配置的搜索 provider（{len(rows)} 个）："]
    for row in rows:
        marker = "（默认）" if row["id"] == default_id else ""
        key_state = "key 已配置" if row["key"] else "key 未设置"
        url = mask_url(row["url"]) or "（默认端点）"
        model = f"，模型 `{row['model']}`" if row["model"] else ""
        lines.append(f"- `{row['id']}`（{row['kind']}）{marker}：{url}，{key_state}{model}")
    lines.append("切换默认：ai search default <名字>；删除：ai search remove <名字>")
    await send_to_event(bot, event, "\n".join(lines))


async def _search_add(bot: Bot, event: Event, args: list[str]) -> None:
    """`ai search add <名字> <kind> [--url <u>] [--key <k>] [--model <m>]`。"""
    if len(args) < 2:
        await send_to_event(bot, event, _SEARCH_USAGE)
        return
    name, kind = args[0], args[1]
    if kind not in search.SEARCH_KINDS:
        await send_to_event(
            bot, event, f"不支持的搜索 provider kind `{kind}`：可选 deepseek / tavily / bocha。"
        )
        return
    opts = _parse_flags(args[2:])
    if kind in ("tavily", "bocha"):
        if not opts.get("key"):
            await send_to_event(bot, event, f"`{kind}` 需要 --key（无继承来源）。")
            return
        if opts.get("url") or opts.get("model"):
            await send_to_event(bot, event, f"`{kind}` 端点与模型已内置，只需要 --key。")
            return
    existing = store.get_search_provider_row(name)
    store.upsert_search_provider(
        name,
        kind,
        url=opts.get("url", ""),
        key=opts.get("key", ""),
        model=opts.get("model", ""),
        updated_by=str(get_user_id(event) or ""),
    )
    verb = "已更新" if existing else "已添加"
    note = ""
    if kind == "deepseek":
        note = "（省略项回退默认端点/模型，key 继承 anthropic 聊天 provider）"
    await send_to_event(
        bot,
        event,
        f"{verb}搜索 provider：`{name}`（{kind}）{note}\n"
        f"设为默认生效：ai search default {name}；查看全部：ai search list",
    )


async def _search_set_default(bot: Bot, event: Event, args: list[str]) -> None:
    """`ai search default <名字>`：选择默认生效的搜索 provider。"""
    if not args:
        await send_to_event(bot, event, _SEARCH_USAGE)
        return
    name = args[0]
    if not store.set_search_default(name):
        await send_to_event(
            bot,
            event,
            f"搜索 provider `{name}` 不存在：`ai search list` 查看已配置，`ai search add` 添加。",
        )
        return
    row = store.get_search_provider_row(name)
    kind = row["kind"] if row else "?"
    await send_to_event(
        bot,
        event,
        f"已将默认搜索 provider 切换为：`{name}`（{kind}）\n查看生效配置：ai search；查看全部：ai search list",
    )


async def _search_remove(bot: Bot, event: Event, args: list[str]) -> None:
    """`ai search remove <名字>`：删除一个搜索 provider。"""
    if not args:
        await send_to_event(bot, event, _SEARCH_USAGE)
        return
    name = args[0]
    if store.delete_search_provider(name):
        await send_to_event(bot, event, f"已删除搜索 provider：`{name}`。")
    else:
        await send_to_event(
            bot, event, f"搜索 provider `{name}` 不存在：`ai search list` 查看已配置。"
        )


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
    await send_to_event(bot, event, "已清理会话历史。" if cleared else "没有可清理的会话历史。")


async def _handle_contexts(bot: Bot, event: Event, args: list[str]) -> None:
    """只读查看 scope 的对话清单（多对话模型）。"""
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
    lines.extend(
        f"  · {category}：{'、'.join(by_category[category])}" for category in sorted(by_category)
    )
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
        await send_to_event(bot, event, "类别必须是：core / computer / bot / web / skill。")
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
        lines = [f"- {row['name']}：{row['description'] or row['prompt'][:40]}" for row in rows]
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
                await send_to_event(bot, event, f"已绑定当前会话为 persona `{rest[0]}`。")
            else:
                await send_to_event(bot, event, f"persona `{rest[0]}` 不存在。")
        else:
            if not scope_key:
                await send_to_event(bot, event, "无法解析当前 scope。")
                return
            if persona.clear_scope(scope_key):
                await send_to_event(bot, event, "已解除当前会话的 persona 绑定，回退默认。")
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


# ------------------------------------------------------------ ai config


def _parse_config_value(key: str, value: str) -> tuple[str, str | None]:
    """校验并规范化一个 config 值；返回 (错误提示, 规范化字符串值)。

    仅处理白名单字段；非白名单返回明确拒绝（其余 AI 配置不支持在线修改）。
    """
    if key == "proxy":
        return "", value
    if key == "render_font":
        return "", value
    if key == "render_theme":
        if value not in ("light", "dark"):
            return f"render_theme 仅支持 light / dark（当前：{value}）。", None
        return "", value
    if key in ("render_timeout_seconds", "render_device_scale"):
        try:
            number = float(value)
        except ValueError:
            return f"{key} 需要数字（当前：{value}）。", None
        if number <= 0:
            return f"{key} 需要大于 0。", None
        return "", str(number)
    if key == "render_emoji":
        normalized = value.strip().lower()
        if normalized in ("1", "true", "yes", "on"):
            return "", "true"
        if normalized in ("0", "false", "no", "off"):
            return "", "false"
        return f"render_emoji 仅支持 true / false（当前：{value}）。", None
    return (
        f"不支持修改 `{key}`：仅代理与渲染相关参数可改"
        f"（proxy / render_font / render_theme / render_timeout_seconds / "
        f"render_device_scale / render_emoji），其余请直接编辑 .env.prod。",
        None,
    )


async def _config_status(bot: Bot, event: Event) -> None:
    """`ai config`：显示当前生效的代理/渲染配置。"""
    cfg = get_config()
    lines = [
        "当前 AI 代理 / 渲染配置（生效值）：",
        f"proxy：{cfg.proxy or '（未设置）'}",
        f"render_font：{cfg.render_font}",
        f"render_theme：{cfg.render_theme}",
        f"render_timeout_seconds：{cfg.render_timeout_seconds}",
        f"render_device_scale：{cfg.render_device_scale}",
        f"render_emoji：{cfg.render_emoji}",
        "在线修改并写盘：ai config set <key> <value>",
        "恢复默认：ai config reset <key>；参数说明：ai config help",
    ]
    await send_to_event(bot, event, "\n".join(lines))


async def _handle_config(bot: Bot, event: Event, args: list[str]) -> None:
    """`ai config`：在线修改代理/渲染参数并写盘（.env.prod），其余参数不可改。"""
    if not args:
        await _config_status(bot, event)
        return
    action, rest = args[0], args[1:]
    if action == "help":
        await send_to_event(bot, event, _CONFIG_USAGE)
        return
    if action == "set":
        if len(rest) < 2:
            await send_to_event(bot, event, "用法：ai config set <key> <value>")
            return
        key, value = rest[0], " ".join(rest[1:]).strip()
        if value in ('""', "''"):
            value = ""
        if key not in CONFIG_EDITABLE:
            await send_to_event(bot, event, _parse_config_value(key, value)[0])
            return
        if not value:
            await send_to_event(
                bot,
                event,
                f"`{key}` 的值不能为空，清除请用 `ai config reset {key}`。",
            )
            return
        error, normalized = _parse_config_value(key, value)
        if error:
            await send_to_event(bot, event, error)
            return
        try:
            write_ai_config_env(AI_ENV_FILE, updates={key: normalized})
        except OSError as exc:
            await send_to_event(bot, event, f"写盘失败：{exc}")
            return
        await send_to_event(
            bot,
            event,
            f"已更新 `{key}`={normalized}（写入 {AI_ENV_FILE}，立即生效；"
            "若进程环境已设置同名 AI_* 变量，以环境变量为准）。",
        )
        return
    if action == "reset":
        if not rest:
            await send_to_event(bot, event, "用法：ai config reset <key>")
            return
        key = rest[0]
        if key not in CONFIG_EDITABLE:
            await send_to_event(bot, event, _parse_config_value(key, "")[0])
            return
        try:
            write_ai_config_env(AI_ENV_FILE, removes=[key])
        except OSError as exc:
            await send_to_event(bot, event, f"写盘失败：{exc}")
            return
        await send_to_event(
            bot, event, f"已清除 `{key}` 的写盘覆盖，恢复代码默认（{AI_ENV_FILE}）。"
        )
        return
    await send_to_event(bot, event, _CONFIG_USAGE)
