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
- ``ai clear [scope]``：清理当前或指定 scope 的会话历史。ADMIN。
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

from . import metrics, providers, store
from .base import get_config, sv
from .config import ProviderConfig, ProviderOptions, mask_url

USAGE = (
    "AI 管理命令：\n"
    "  ai provider list / default <id> / use <id> / reset / add <id> / remove <id>\n"
    "  ai status / stats [provider_id] / clear [scope]\n"
    "用 ai provider add 查看参数说明。"
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
    lines = [
        f"默认 provider：`{config.default}`"
        if config.default
        else "默认 provider：未设置",
        f"当前 scope 绑定：`{bound}`" if bound else "当前 scope 绑定：无（回退默认）",
        f"历史长度限制：{config.max_history_messages} 条",
        f"渲染超时：{config.render_timeout_seconds}s",
        f"渲染主题：{config.render_theme}",
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
    if args:
        # 显式指定 scope_key 清理（ADMIN 即可）。
        cleared = store.clear_session(args[0])
    else:
        scope_key = event_scope_key(bot, event)
        if scope_key is None:
            await send_to_event(bot, event, "无法解析当前会话 scope。")
            return
        cleared = store.clear_session(scope_key)
    await send_to_event(
        bot, event, "已清理会话历史。" if cleared else "没有可清理的会话历史。"
    )
