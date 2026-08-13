"""AI 管理插件：provider 配置、scope provider 切换、用量查询。

命令与权限（全部平台无关）：
- ``ai provider list``：列出 provider 信息（url 掩码，不显示 key）。ADMIN。
- ``ai provider default <id>``：设置全局默认 provider。SUPERUSER。
- ``ai provider use <id>``：把当前群 scope 绑定到指定 provider。群内 ADMIN+，私聊拒绝。
- ``ai provider reset``：清除当前群 scope 绑定。群内 ADMIN+，私聊拒绝。
- ``ai provider add <id> [--url ... --key ... --kind ... --model ...]``：新增/更新。SUPERUSER。
- ``ai provider remove <id>``：删除 provider，先清理 scope 绑定；默认 provider 不允许直接删除。SUPERUSER。
- ``ai status``：显示默认 provider、当前绑定、历史限制、渲染配置。ADMIN。
- ``ai stats [provider_id]``：显示 token / 缓存 / 延迟统计。ADMIN。
- ``ai clear [scope]``：清空当前或指定 scope 的当前激活对话。ADMIN。
- ``ai contexts [scope]``：只读查看 scope 的对话清单（多对话模型）。ADMIN。
"""

from __future__ import annotations

from dataclasses import replace

from nonebot.adapters import Bot, Event

from hoshino.platform import (
    event_scope_key,
    get_group_id,
    get_user_id,
    group_scope_key,
    platform_key,
    send_to_event,
)
from hoshino.platform.depends import ParamText
from hoshino.platform.permission import ADMIN
from hoshino.platform.superuser import is_superuser

from . import (
    _deps as deps,
    _metrics as metrics,
    _persona as persona,
    _providers as providers,
    _sessions,
    _store as store,
    _tools as tools,
)
from ._base import get_config, sv
from ._config import ProviderConfig, ProviderOptions, mask_url

# 子包目录不会被 load_plugins 遍历，这里在插件加载期（controlled_modules 已建立）
# 显式导入以注册 ai task matcher 与 scheduler hooks。不能提前到 ai/__init__.py。
from ._task import commands as _task_commands  # noqa: F401

USAGE = (
    "AI 管理命令：\n"
    "  ai provider list / default <id> / use <id> / reset / add <id> / remove <id>\n"
    "  ai status / stats [provider_id] / clear [scope] / contexts [scope]\n"
    "  ai tools list [scope] [chat|task] / ai tools on|off <cat> <chat|task> [scope]\n"
    "  ai persona list/show/create/update/use/reset/global/delete\n"
    "用 ai provider add / ai persona create 查看参数说明。"
)

_TOOLS_USAGE = (
    "AI 工具管理：\n"
    "  ai tools list [chat|task]           查看可用工具（管理员）\n"
    "  ai tools on|off <类别> [chat|task]  开启/关闭类别（超管，默认 chat）\n"
    "类别：core / computer / bot / web / skill"
)


def _tool_name(tool) -> str:
    return getattr(tool, "name", None) or getattr(tool, "__name__", None) or "?"


_PERSONA_USAGE = (
    "用法：\n"
    "  ai persona list\n"
    "  ai persona show <name>\n"
    "  ai persona create <name> [--gender <g>] [--personality <p>] [--description <d>]\n"
    "  ai persona update <name> [--gender <g>] [--personality <p>] [--description <d>]\n"
    "  ai persona use <name>   绑定当前 scope（ADMIN）\n"
    "  ai persona reset        解除当前 scope 绑定（ADMIN）\n"
    "  ai persona global <name>|off   设置/清除全局（SUPERUSER）\n"
    "  ai persona delete <name>       删除（SUPERUSER）"
)

_ADD_USAGE = (
    "用法：ai provider add <id> --url <url> --key <key> [选项]\n"
    "选项：--kind openai_chat|openai_responses|anthropic --model <m> "
    "--temperature <t> --max-tokens <n> --timeout <s>"
)

_KNOWN_KINDS = ("openai_chat", "openai_responses", "anthropic")

# only_group=False：让私聊也能触发，从而在 handler 内对 use/reset 给出
# “私聊不允许”的明确提示，而不是静默无响应。
aicmd = sv.on_command("ai", permission=ADMIN, compact=False, only_group=False)


@aicmd.handle()
async def _(bot: Bot, event: Event, text: str = ParamText()):
    args = text.strip().split()
    if not args:
        await send_to_event(bot, event, USAGE)
        return
    sub, rest = args[0], args[1:]
    if sub == "provider":
        await _handle_provider(bot, event, rest)
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
    """把 ``--key value`` 解析成 dict。值缺失时记空串。"""
    opts: dict[str, str] = {}
    index = 0
    while index < len(args):
        arg = args[index]
        if arg.startswith("--"):
            key = arg[2:].replace("-", "_")
            value = args[index + 1] if index + 1 < len(args) else ""
            opts[key] = value
            index += 2
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
        await _provider_use(bot, event, rest, config)
    elif action == "reset":
        await _provider_reset(bot, event)
    elif action == "add":
        await _provider_add(bot, event, rest, config)
    elif action == "remove":
        await _provider_remove(bot, event, rest, config)
    else:
        await send_to_event(bot, event, USAGE)


async def _provider_list(bot: Bot, event: Event, config) -> None:
    if not config.providers:
        await send_to_event(bot, event, "未配置任何 provider。")
        return
    lines = ["已配置的 provider："]
    for pid, pc in config.providers.items():
        mark = " ← 默认" if pid == config.default else ""
        lines.append(
            f"- `{pid}` kind={pc.config.kind} model={pc.config.model or '-'} "
            f"url={mask_url(pc.url)}{mark}"
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
    if not config.has_provider(pid):
        await send_to_event(bot, event, f"provider `{pid}` 不存在。")
        return
    sv.save_config(replace(config, default=pid))
    await send_to_event(bot, event, f"已设置全局默认 provider：`{pid}`")


async def _provider_use(bot: Bot, event: Event, args: list[str], config) -> None:
    gid = get_group_id(event)
    if gid is None:
        await send_to_event(bot, event, "私聊不允许切换 provider。")
        return
    if not args:
        await send_to_event(bot, event, "用法：ai provider use <id>")
        return
    pid = args[0]
    if not config.has_provider(pid):
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


async def _provider_add(bot: Bot, event: Event, args: list[str], config) -> None:
    if not _require_superuser(bot, event):
        await send_to_event(bot, event, "仅 SUPERUSER 可新增/修改 provider。")
        return
    if not args:
        await send_to_event(bot, event, _ADD_USAGE)
        return
    pid = args[0]
    opts = _parse_flags(args[1:])
    kind = opts.get("kind", "openai_chat")
    if kind not in _KNOWN_KINDS:
        await send_to_event(
            bot, event, "kind 必须是 openai_chat / openai_responses / anthropic。"
        )
        return
    try:
        options = ProviderOptions(
            kind=kind,
            model=opts.get("model", ""),
            temperature=float(opts["temperature"]) if opts.get("temperature") else None,
            max_tokens=int(opts["max_tokens"]) if opts.get("max_tokens") else None,
            timeout_seconds=float(opts["timeout"]) if opts.get("timeout") else None,
        )
    except ValueError:
        await send_to_event(
            bot, event, "temperature / max-tokens / timeout 必须是数字。"
        )
        return
    new_pc = ProviderConfig(
        url=opts.get("url", ""), key=opts.get("key", ""), config=options
    )
    existed = pid in config.providers
    providers_map = dict(config.providers)
    providers_map[pid] = new_pc
    sv.save_config(replace(config, providers=providers_map))
    providers.clear_agent_cache()
    verb = "更新" if existed else "新增"
    await send_to_event(bot, event, f"已{verb} provider `{pid}`（kind={kind}）。")


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
    if not config.has_provider(pid):
        await send_to_event(bot, event, f"provider `{pid}` 不存在。")
        return
    store.clear_provider_references(pid)
    providers_map = dict(config.providers)
    del providers_map[pid]
    sv.save_config(replace(config, providers=providers_map))
    providers.clear_agent_cache()
    await send_to_event(bot, event, f"已删除 provider `{pid}`。")


async def _handle_status(bot: Bot, event: Event) -> None:
    config = get_config()
    scope_key = event_scope_key(bot, event)
    bound = store.get_scope_provider(scope_key) if scope_key else None
    provider_id = bound or config.default
    provider_cfg = config.get_provider(provider_id) if provider_id else None
    # 原生联网搜索只在 anthropic / openai_responses kind 上生效（服务端 web_search）。
    native_search = (
        config.web_search_native
        and provider_cfg is not None
        and provider_cfg.config.kind in ("anthropic", "openai_responses")
    )
    lines = [
        f"默认 provider：`{config.default}`"
        if config.default
        else "默认 provider：未设置",
        f"当前 scope 绑定：`{bound}`" if bound else "当前 scope 绑定：无（回退默认）",
        f"历史长度限制：{config.max_history_messages} 条",
        f"渲染超时：{config.render_timeout_seconds}s",
        f"渲染主题：{config.render_theme}",
        f"原生联网搜索：{'开（服务端 web_search）' if native_search else '关'}"
        f"（工具重试预算 {config.tool_max_retries} 次）",
        f"provider 数量：{len(config.providers)}",
    ]
    await send_to_event(bot, event, "\n".join(lines))


async def _handle_stats(bot: Bot, event: Event, args: list[str]) -> None:
    pid = args[0] if args else None
    config = get_config()
    if pid is not None and not config.has_provider(pid):
        await send_to_event(bot, event, f"provider `{pid}` 不存在。")
        return
    aggregate = store.aggregate_usage(provider_id=pid)
    await send_to_event(bot, event, metrics.format_stats(aggregate, provider_id=pid))


async def _handle_clear(bot: Bot, event: Event, args: list[str]) -> None:
    manager = _sessions.conversation_manager
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
    summaries = _sessions.conversation_manager.list_summaries(scope_key)
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
        try:
            p = persona.create_persona(
                name,
                gender=opts.get("gender", ""),
                personality=opts.get("personality", ""),
                description=opts.get("description", ""),
                created_by=user,
            )
        except ValueError as exc:
            await send_to_event(bot, event, str(exc))
            return
        await send_to_event(bot, event, f"已创建 persona `{p['name']}`：{p['prompt']}")
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
        p = persona.update_persona(
            name,
            gender=opts.get("gender"),
            personality=opts.get("personality"),
            description=opts.get("description"),
        )
        if p is None:
            await send_to_event(bot, event, f"persona `{name}` 不存在。")
            return
        await send_to_event(bot, event, f"已更新 persona `{p['name']}`：{p['prompt']}")
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
