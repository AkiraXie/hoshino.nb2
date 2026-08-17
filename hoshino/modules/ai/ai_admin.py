"""AI 管理插件：provider / model / vision / scope 配置与用量查询（**仅超级用户可用**）。

模型管理语义：
- ``ai model``：显示当前使用的文本模型（含来源）与操作提示。
- ``ai model list``：调用 provider API 获取**真实可用模型列表**（本地不存 model-list）。
- ``ai model set <模型>``：设置文本模型（默认槽位）。设置前实时校验模型在 API
  可用列表内，设置后回显当前生效模型。
- ``ai model reset``：清除本群文本模型覆盖，回退 provider 默认。

vision 管理语义（独立 provider + 模型，与文本模型解耦）：
- ``ai vision``：显示当前 scope 的 vision 配置（provider + 模型，含来源）。
- ``ai vision set <provider> <模型>`` / ``ai vision set <provider>/<模型>``：
  设置本群 vision 的 provider 与模型；``ai vision set none`` 显式禁用。
- ``ai vision reset``：清除本群 vision 配置，回退全局默认。
- ``ai vision default <provider> <模型>``：设置全局默认 vision（仅 SUPERUSER）。

搜索管理语义（独立搜索 provider，与聊天 provider 解耦，默认 deepseek；
支持配置多个 provider，再选一个作为默认生效）：
- ``ai search``：显示当前生效的搜索 provider（kind/端点/模型；key 只显示已配置/未设置）。
- ``ai search add <名字> <kind> [--url <u>] [--key <k>] [--model <m>]``：
  添加/更新搜索 provider（名字自定，多 provider 并存）。deepseek 省略项回退默认
  端点/模型，key 继承 anthropic 聊天 provider；tavily/bocha 只需要 --key
  （端点已内置 api.tavily.com / api.bocha.cn）。
- ``ai search default <名字>``（``set`` 同义）：把某个 provider 设为默认生效。
- ``ai search list``：列出所有已配置的 provider（默认标记）。
- ``ai search remove <名字>``：删除一个 provider。
- ``ai config`` 仅代理/渲染语义，不涉及搜索；搜索走 ``ai search``。

provider 管理语义：
- ``ai provider``：显示全局默认与当前群绑定 + 操作提示。
- ``ai provider set <id>``（兼容 ``use``）：绑定当前群；``default <id>`` 设全局默认；
  ``reset`` 清除绑定；``list`` 列出已配置。
- ``ai setup <id> --url <url> --key <key> [--text <m>]``：
  一键配置：新增/更新 provider + 设默认 + 绑定当前群（唯一新增入口）。
- ``ai provider remove <id>``：删除 provider。

其余：``ai status``、``ai stats [provider_id]``、``ai clear [scope]``、
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
    "快速上手：\n"
    "  ai setup <id> --url <u> --key <k> [--text <m>]  一键配置 provider\n"
    "  ai model              查看当前文本模型\n"
    "  ai model list         获取真实可用模型（provider API）\n"
    "  ai model set <模型>   设置文本模型（默认槽位）\n"
    "  ai vision             查看/设置看图模型（独立 provider + 模型）\n"
    "  ai search             查看/管理搜索 provider（多 provider，选默认生效）\n"
    "  ai provider           查看当前 provider\n"
    "  ai provider set <id>  绑定当前群到指定 provider\n"
    "其他：\n"
    "  ai provider list / default <id> / reset / remove\n"
    "  ai model reset [text] / ai vision set|reset|default\n"
    "  ai search list / add <名字> <kind> / default|set <名字> / remove\n"
    "  ai status / ai stats [provider_id]\n"
    "  ai clear [scope] / ai contexts [scope] / ai tools ... / ai persona ...\n"
    "  ai config [set <key> <value> | reset <key>]  在线改代理/渲染参数并写盘\n"
    "  ai task research|plan|status|list|approve|deny|cancel|workspaces\n"
    "用 ai setup / ai vision / ai search / ai persona / ai config 查看参数说明。"
)

_SETUP_USAGE = (
    "用法：ai setup <provider_id> --url <url> --key <key> [--text <m>]\n"
    "  [--use-proxy [1|0]]   走全局代理 OUTSIDE_PROXY（默认保持原值，显式 0 关闭）\n"
    "一步完成：新增/更新 provider（openai_chat 兼容）、设全局默认、绑定当前群、"
    "把 --text 设为默认文本模型；之后 ai model / ai status 查看生效配置，\n"
    "看图（vision）单独配置：ai vision set <provider> <模型>。"
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
    "  ai model              查看当前文本模型\n"
    "  ai model list         获取真实可用模型（provider API）\n"
    "  ai model set <模型>   设置文本模型（默认槽位）\n"
    "  ai model reset [text] 清除本群文本模型覆盖，回退 provider 默认\n"
    "示例：ai model set deepseek-v4-flash\n"
    "看图（vision）请用 `ai vision`：独立配置 provider + 模型。"
)

_VISION_USAGE = (
    "用法：\n"
    "  ai vision                             查看当前 vision 配置\n"
    "  ai vision set <provider> <模型>        设置本群 vision provider 与模型\n"
    "  ai vision set <provider>/<模型>        同上（斜杠分隔）\n"
    "  ai vision set none                     本群显式禁用 vision\n"
    "  ai vision reset                        清除本群 vision 配置，回退全局默认\n"
    "  ai vision default <provider> <模型>    设置全局默认 vision（仅 SUPERUSER）\n"
    "  ai vision default none                 清除全局默认 vision\n"
    "示例：ai vision set opencode-go mimo-v2.5；ai vision set opencode-go/mimo-v2.5"
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
    "回退默认端点/模型，key 继承 anthropic 聊天 provider；tavily/bocha 只需\n"
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
        # 裸 `ai`：直接给状态总览（含看图引导），比命令清单更自然。
        await _handle_status(bot, event)
        return
    sub, rest = args[0], args[1:]
    match sub:
        case "help" | "?":
            await send_to_event(bot, event, USAGE)
        case "setup":
            await _handle_setup(bot, event, rest)
        case "provider":
            await _handle_provider(bot, event, rest)
        case "model":
            await _handle_model(bot, event, rest)
        case "vision":
            await _handle_vision(bot, event, rest)
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
    match action:
        case "list":
            await _provider_list(bot, event, config)
        case "set" | "use":
            await _provider_set(bot, event, rest)
        case "default":
            await _provider_default(bot, event, rest, config)
        case "reset":
            await _provider_reset(bot, event)
        case "remove":
            await _provider_remove(bot, event, rest, config)
        case _:
            await send_to_event(bot, event, USAGE)


async def _provider_status(bot: Bot, event: Event) -> None:
    """`ai provider`：当前 provider（全局默认 + 本群绑定）+ 操作提示。"""
    config = get_config()
    scope_key = event_scope_key(bot, event)
    bound = store.get_scope_provider(scope_key) if scope_key else None
    lines = [
        f"全局默认 provider：`{config.default}`" if config.default else "全局默认 provider：未设置",
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
        proxy_flag = " proxy=on" if record.use_proxy else ""
        lines.append(
            f"- `{record.id}` kind={record.kind} "
            f"text={record.default_text_model or '-'} "
            f"url={mask_url(record.url)}{proxy_flag}{mark}"
        )
    lines.append("模型列表用 `ai model list` 实时获取；vision 单独配置：ai vision。")
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
            default_text_model=opts.get("text", ""),
            use_proxy=use_proxy,
        )
    )
    providers.clear_agent_cache()

    lines = [f"已{'更新' if old is not None else '新增'} provider `{pid}`。"]
    store.set_global_value("default_provider", pid)
    lines.append("已设为全局默认 provider。")
    gid = get_group_id(event)
    if gid is not None:
        scope_key = group_scope_key(gid, platform=platform_key(bot))
        store.set_scope_provider(scope_key, pid, updated_by=str(get_user_id(event) or ""))
        lines.append("已绑定当前群。")
    if opts.get("text"):
        lines.append(f"文本模型：`{opts['text']}`。")
    lines.append(f"全局代理：{'启用' if use_proxy else '未启用'}（use_proxy）。")
    lines.append("看图（vision）需单独配置：`ai vision set <provider> <模型>`。")
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
        await send_to_event(bot, event, "当前默认 provider 不允许直接删除，请先修改 default。")
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
    """`ai model`：当前使用的文本模型（含来源）+ 操作提示。"""
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
    text_model = provider.resolve_text_model(scope_key, pid)
    overrides = store.get_scope_model_overrides(scope_key or "")
    source_text = "本群覆盖" if overrides["text_model"] else "provider 默认"
    lines = [
        f"provider：`{pid}`" + ("" if not bound else "（本群绑定）"),
        f"文本模型：`{text_model or '（未设置）'}`（{source_text}）",
        "改文本：ai model set <模型>；看图：ai vision（独立 provider + 模型）",
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
        record,
        proxy=provider.resolve_effective_proxy(record, config.proxy),
        verify=config.web_fetch_verify_ssl,
    )
    if not models:
        await send_to_event(
            bot, event, f"获取 provider `{pid}` 的模型列表失败（网络或端点不支持）。"
        )
        return
    text_model = provider.resolve_text_model(scope_key, pid)
    lines = [f"provider `{pid}` 可用模型（{len(models)} 个，来自 API）："]
    for model in models:
        mark = "当前文本" if model == text_model else ""
        lines.append(f"- {model}" + (f"（{mark}）" if mark else ""))
    lines.append("设置文本：ai model set <模型>；vision 独立配置：ai vision")
    await send_to_event(bot, event, "\n".join(lines))


async def _model_set(bot: Bot, event: Event, scope_key: str, args: list[str]) -> None:
    """`ai model set [text] <模型>`：设置文本模型；实时校验后在 provider API 可用列表内。

    设置后回显当前生效文本模型。
    """
    if not args:
        await send_to_event(bot, event, _MODEL_USAGE)
        return
    if len(args) == 2 and args[0] == "text":
        model = args[1]
    elif len(args) == 1:
        model = args[0]
    else:
        await send_to_event(bot, event, "用法：ai model set [text] <模型>")
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

    record = provider.get_provider(pid)
    available = await provider.fetch_available_models(
        record,
        proxy=provider.resolve_effective_proxy(record, config.proxy),
        verify=config.web_fetch_verify_ssl,
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

    store.set_scope_text_model(scope_key, model, updated_by=str(get_user_id(event) or ""))
    await _echo_models(bot, event, scope_key, pid, warning)


async def _model_reset(bot: Bot, event: Event, scope_key: str, args: list[str]) -> None:
    """`ai model reset [text]`：清除文本模型覆盖回退 provider 默认，并回显。"""
    if args and args[0] != "text":
        await send_to_event(bot, event, "用法：ai model reset [text]")
        return
    cleared = store.clear_scope_model_override(scope_key, "text")
    if not cleared:
        await send_to_event(bot, event, "本群当前没有文本模型覆盖。")
        return
    config = get_config()
    pid = await _scope_provider_id(scope_key, config)
    if pid is not None:
        await _echo_models(
            bot, event, scope_key, pid, "（已清除本群文本模型覆盖，回退 provider 默认）"
        )
    else:
        await send_to_event(bot, event, "已清除本群文本模型覆盖。")


async def _echo_models(bot: Bot, event: Event, scope_key: str, pid: str, extra: str = "") -> None:
    """设置/重置后回显当前生效文本模型（含操作提示）。"""
    text_model = provider.resolve_text_model(scope_key, pid)
    await send_to_event(
        bot,
        event,
        f"当前文本模型：`{text_model or '（未设置）'}`{extra}\n"
        "改：ai model set <模型>；看图：ai vision（独立 provider + 模型）",
    )


async def _handle_status(bot: Bot, event: Event) -> None:
    """`ai status` / 裸 `ai`：只显示当前 provider、文本模型与 vision。

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
    text_model = provider.resolve_text_model(scope_key, provider_id)
    vision_provider_id, vision_model = provider.resolve_vision(scope_key)
    vision_line = (
        f"vision：`{vision_model}`（`{vision_provider_id}`）"
        if vision_model
        else "vision：`（未设置）`"
    )
    lines = [
        f"当前 provider：`{provider_id}`",
        f"文本模型：`{text_model or '（未设置）'}`",
        vision_line,
    ]
    await send_to_event(bot, event, "\n".join(lines))


# ------------------------------------------------------------ vision


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


async def _handle_vision(bot: Bot, event: Event, args: list[str]) -> None:
    """``ai vision``：查看/设置本群 vision（独立 provider + 模型）。"""
    if not args:
        await _vision_status(bot, event)
        return
    action, rest = args[0], args[1:]
    if action in ("show", "status"):
        await _vision_status(bot, event)
        return
    if action == "default":
        await _vision_default(bot, event, rest)
        return
    gid = get_group_id(event)
    if gid is None:
        await send_to_event(bot, event, "vision 设置仅限群聊。")
        return
    scope_key = group_scope_key(gid, platform=platform_key(bot))
    if action == "set":
        await _vision_set(bot, event, scope_key, rest)
    elif action == "reset":
        await _vision_reset(bot, event, scope_key, rest)
    else:
        await send_to_event(bot, event, _VISION_USAGE)


async def _vision_status(bot: Bot, event: Event) -> None:
    """`ai vision`：当前 scope 的 vision 配置（provider + 模型，含来源）。"""
    scope_key = event_scope_key(bot, event)
    overrides = store.get_scope_model_overrides(scope_key or "")
    vision_provider_id, vision_model = provider.resolve_vision(scope_key)
    if overrides["vision_model"] == provider.VISION_DISABLED:
        source = "本群已禁用"
    elif overrides["vision_provider"] and overrides["vision_model"]:
        source = "本群配置"
    elif store.get_global_value(provider.VISION_GLOBAL_PROVIDER):
        source = "全局默认"
    else:
        source = "未配置"
    current = f"`{vision_provider_id}` / `{vision_model}`" if vision_model else "`（未设置）`"
    lines = [
        f"vision：{current}（{source}）",
        "设置本群：ai vision set <provider> <模型>（或 <provider>/<模型>）",
        "禁用本群：ai vision set none；清除回退全局：ai vision reset",
        "全局默认（超管）：ai vision default <provider> <模型>",
    ]
    await send_to_event(bot, event, "\n".join(lines))


async def _echo_vision(bot: Bot, event: Event, scope_key: str, extra: str = "") -> None:
    """设置/重置后回显当前生效 vision（含操作提示）。"""
    vision_provider_id, vision_model = provider.resolve_vision(scope_key)
    current = f"`{vision_provider_id}` / `{vision_model}`" if vision_model else "`（未设置）`"
    await send_to_event(
        bot,
        event,
        f"当前 vision：{current}{extra}\n"
        "改：ai vision set <provider> <模型>；禁用：ai vision set none",
    )


async def _vision_set(bot: Bot, event: Event, scope_key: str, args: list[str]) -> None:
    """`ai vision set <provider> <模型>` / `<provider>/<模型>` / ``none``。"""
    actor = str(get_user_id(event) or "")
    if not args:
        await send_to_event(bot, event, _VISION_USAGE)
        return
    if args[0] == "none":
        if len(args) != 1:
            await send_to_event(bot, event, "用法：ai vision set none")
            return
        store.set_scope_vision(scope_key, "", provider.VISION_DISABLED, updated_by=actor)
        await _echo_vision(bot, event, scope_key, "（本群已禁用 vision）")
        return
    spec = _parse_provider_model(args)
    if spec is None:
        await send_to_event(
            bot, event, "用法：ai vision set <provider> <模型>（或 <provider>/<模型>）"
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

    store.set_scope_vision(scope_key, pid, model, updated_by=actor)
    note = "（vision 模型需真正支持看图，若识别失败请换模型）"
    await _echo_vision(bot, event, scope_key, warning + note)


async def _vision_reset(bot: Bot, event: Event, scope_key: str, args: list[str]) -> None:
    """`ai vision reset`：清除本群 vision 配置，回退全局默认。"""
    if args:
        await send_to_event(bot, event, "用法：ai vision reset")
        return
    overrides = store.get_scope_model_overrides(scope_key)
    if not overrides["vision_provider"] and not overrides["vision_model"]:
        await send_to_event(bot, event, "本群当前没有 vision 配置。")
        return
    store.set_scope_vision(scope_key, "", "", updated_by=str(get_user_id(event) or ""))
    await _echo_vision(bot, event, scope_key, "（已清除本群 vision 配置，回退全局默认）")


async def _vision_default(bot: Bot, event: Event, args: list[str]) -> None:
    """`ai vision default <provider> <模型>`：设置全局默认 vision（仅 SUPERUSER）。"""
    if not _require_superuser(bot, event):
        await send_to_event(bot, event, "仅 SUPERUSER 可设置全局默认 vision。")
        return
    if not args:
        await send_to_event(bot, event, "用法：ai vision default <provider> <模型>|none")
        return
    if args[0] == "none":
        if len(args) != 1:
            await send_to_event(bot, event, "用法：ai vision default none")
            return
        store.clear_global_value(provider.VISION_GLOBAL_PROVIDER)
        store.clear_global_value(provider.VISION_GLOBAL_MODEL)
        await send_to_event(bot, event, "已清除全局默认 vision。")
        return
    spec = _parse_provider_model(args)
    if spec is None:
        await send_to_event(
            bot, event, "用法：ai vision default <provider> <模型>（或 <provider>/<模型>）"
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
            sample = "、".join(f"`{m}`" for m in available[:20])
            await send_to_event(
                bot,
                event,
                f"模型 `{model}` 不在 provider `{pid}` 的可用列表中（API 获取）。\n"
                f"可用：{sample}{'…' if len(available) > 20 else ''}",
            )
            return
    else:
        warning = "（无法连接 provider 校验，已直接设置）"
    store.set_global_value(provider.VISION_GLOBAL_PROVIDER, pid)
    store.set_global_value(provider.VISION_GLOBAL_MODEL, model)
    await send_to_event(bot, event, f"已设置全局默认 vision：`{pid}` / `{model}`{warning}")


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
        await send_to_event(
            bot,
            event,
            "当前未配置搜索 provider：`ai search add <名字> <deepseek|tavily|bocha> ...`\n"
            "（默认 deepseek 需 anthropic 兼容聊天 provider 或显式 --key）。",
        )
        return
    source = "自定义" if default_id else "默认（继承 anthropic 聊天 provider）"
    label = f"`{default_id}`（`{cfg.kind}`）" if default_id else f"`{cfg.kind}`"
    lines = [
        f"搜索 provider：{label}（{source}）",
        f"端点：{mask_url(cfg.url)}",
        "API key：已配置" if cfg.key else "API key：未设置",  # 不展示 key（含脱敏）
    ]
    if cfg.kind == "deepseek":
        lines.append(f"模型：`{cfg.model}`")
    lines.append(
        "管理：ai search list 查看全部；ai search add 添加；ai search default <名字> 切换默认"
    )
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
