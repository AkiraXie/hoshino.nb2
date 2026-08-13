"""AI 聊天插件：以 ``#`` 开头触发对话，支持每 scope 多对话（上下文）管理。

- 群聊/私聊均可用，不要求 @机器人；只感知 ``#`` 前缀消息。
- ``#`` 命名空间保留词为控制命令（整词精确匹配）：
  ``#new [name]`` 新建并切换 / ``#switch|sw <name>`` 切换 / ``#list|ls`` 列出 /
  ``#clear`` 清空当前对话；其余内容一律按聊天处理（``#new 特性介绍`` 是提问）。
- 上下文（Session→Conversation，对齐 AstrBot）：内存缓存 + SQLite write-through，
  见 ``_sessions.py``；轮次按 scope 锁串行化，run 进行中再收 ``#`` 回忙提示。
- 执行护栏（持久化不替代超时，见 aichat-context-timeout-plan.md §3）：
  run 墙钟 ``chat_run_timeout_seconds`` + ``UsageLimits(chat_max_requests)``。
  超时/超限把本轮提问写入上下文可续问；provider 异常不写。
- 模型输出 Markdown 先渲染为图片；渲染失败（超时/浏览器异常）回退纯文本。
- 含图输入只加提示文案，不做多模态理解。
- 日志只记录 provider id、scope、耗时、错误类型，不打印 key 或完整历史。
"""

from __future__ import annotations

import asyncio
import time
import traceback

from nonebot.adapters import Bot, Event
from nonebot_plugin_alconna.uniseg import UniMessage
from pydantic_ai.exceptions import UsageLimitExceeded
from pydantic_ai.usage import UsageLimits

from hoshino.platform import (
    event_scope_key,
    get_group_id,
    get_plaintext,
    send_to_event,
)

from . import (
    _context as context,
    _deps as deps,
    _errors as errors,
    _metrics as metrics,
    _providers as providers,
    _rendering as rendering,
    _runner as runner,
    _sessions,
)
from ._base import (
    get_config,
    provider_error_message,
    resolve_provider,
    sv,
)

# 默认 block=True，避免 ``#`` 消息继续命中其他 on_message 规则。
chat = sv.on_startswith(
    "#", only_group=False, only_to_me=False, priority=10, block=True
)


@chat.handle()
async def _(bot: Bot, event: Event):
    body = get_plaintext(event).removeprefix("#").strip()
    if not body:
        return
    scope_key = event_scope_key(bot, event)
    if scope_key is None:
        return

    control = _parse_control(body)
    if control is not None:
        await _handle_control(bot, event, scope_key, control)
        return

    lock = _sessions.conversation_manager.turn_lock(scope_key)
    if lock.locked():
        await send_to_event(bot, event, "上一条消息还在处理中，请稍候再试。")
        return
    async with lock:
        await _handle_chat_turn(bot, event, scope_key, body)


# ------------------------------------------------------------ 控制命令


def _parse_control(body: str) -> tuple[str, str | None] | None:
    """识别 ``#`` 命名空间保留词；整词精确匹配，多余内容一律按聊天处理。"""
    tokens = body.split()
    head = tokens[0].lower()
    rest = tokens[1:]
    if head == "new" and len(rest) <= 1:
        return ("new", rest[0] if rest else None)
    if head in ("switch", "sw") and len(rest) == 1:
        return ("switch", rest[0])
    if head in ("list", "ls") and not rest:
        return ("list", None)
    if head == "clear" and not rest:
        return ("clear", None)
    return None


async def _handle_control(
    bot: Bot, event: Event, scope_key: str, control: tuple[str, str | None]
) -> None:
    manager = _sessions.conversation_manager
    action, arg = control

    if action == "new":
        try:
            conv = manager.create(scope_key, arg)
        except ValueError as exc:
            await send_to_event(bot, event, str(exc))
            return
        await send_to_event(bot, event, f"已新建并切换到对话 `{conv.name}`。")
        return

    if action == "switch":
        conv = manager.switch(scope_key, arg or "")
        if conv is None:
            names = "、".join(s["name"] for s in manager.list_summaries(scope_key))
            await send_to_event(
                bot, event, f"对话 `{arg}` 不存在。可用：{names or '（无）'}"
            )
            return
        await send_to_event(bot, event, f"已切换到对话 `{conv.name}`。")
        return

    if action == "list":
        summaries = manager.list_summaries(scope_key)
        if not summaries:
            await send_to_event(bot, event, "当前会话还没有对话。")
            return
        lines = ["本会话的对话："]
        for s in summaries:
            mark = "* " if s["active"] else "- "
            updated = time.strftime("%m-%d %H:%M", time.localtime(s["updated_at"]))
            lines.append(f"{mark}{s['name']}（{s['count']} 条，{updated} 更新）")
        await send_to_event(bot, event, "\n".join(lines))
        return

    if action == "clear":
        if not await _can_clear(bot, event):
            await send_to_event(bot, event, "清空对话历史需要管理员权限。")
            return
        cleared = manager.clear_active(scope_key)
        await send_to_event(
            bot,
            event,
            "已清空当前对话历史。" if cleared else "当前对话没有可清空的历史。",
        )


async def _can_clear(bot: Bot, event: Event) -> bool:
    """私聊本人任意；群内 ADMIN / OWNER / SUPERUSER。"""
    if get_group_id(event) is None:
        return True
    permissions = await deps.build_permission_snapshot(bot, event)
    return permissions.is_admin or permissions.is_superuser


# ---------------------------------------------------------------- 聊天


async def _handle_chat_turn(bot: Bot, event: Event, scope_key: str, prompt: str):
    """单轮聊天：解析 provider → 读当前对话上下文 → run（带护栏）→ 渲染回复。"""
    manager = _sessions.conversation_manager
    config = get_config()
    provider_id = resolve_provider(scope_key, config)
    if provider_id is None:
        await send_to_event(bot, event, provider_error_message(config))
        return
    provider_config = config.get_provider(provider_id)
    if provider_config is None:
        await send_to_event(bot, event, "AI 配置异常：provider 不存在。")
        return

    conv = manager.get_active(scope_key)
    history = context.prepare_history(scope_key, conv.messages, config)

    model_name = provider_config.config.model or provider_id
    permissions = await deps.build_permission_snapshot(bot, event)
    agent_deps = deps.construct_chat_deps(
        bot,
        event,
        config,
        permissions,
        provider_id=provider_id,
        model=model_name,
    )
    agent = providers.build_agent(
        provider_id,
        provider_config,
        proxy=config.proxy,
        web_search_native=config.web_search_native,
        tool_max_retries=config.tool_max_retries,
    )
    # 失败可观测性：记录本轮发起过的工具调用，异常时随日志输出定位是
    # 模型侧问题还是工具侧问题（如 web_search）。
    last_tools: list[str] = []

    def _track_tools(ev: runner.RunEvent) -> None:
        last_tools.extend(runner.tool_calls_from_node(ev.node))

    try:
        result = await asyncio.wait_for(
            runner.run_agent(
                agent,
                prompt,
                deps=agent_deps,
                message_history=history,
                usage_limits=UsageLimits(request_limit=config.chat_max_requests),
                on_event=_track_tools,
            ),
            timeout=config.chat_run_timeout_seconds,
        )
    except (TimeoutError, UsageLimitExceeded) as exc:
        # 护栏触发：丢弃本次执行，但把提问留在上下文，下一轮可续问。
        agent_deps.telemetry.record_error(type(exc).__name__)
        manager.append_prompt_only(scope_key, prompt, provider_id)
        reason = "超时" if isinstance(exc, TimeoutError) else "超出步数限制"
        sv.logger.warning(
            f"AI 请求{reason} provider={provider_id} scope={scope_key} conv={conv.name}"
        )
        await send_to_event(
            bot,
            event,
            f"处理{reason}，问题已保留在上下文，可直接续问或换种问法。",
        )
        return
    except Exception as exc:
        # 完整错误详情（message + body/status/tool）+ 失败前工具调用；
        # traceback 只在 DEBUG 级别落，避免 WARNING 刷屏。
        detail = errors.format_exception_detail(exc)
        agent_deps.telemetry.record_error(detail)
        sv.logger.warning(
            f"AI 请求失败 provider={provider_id} scope={scope_key} conv={conv.name} "
            f"error={type(exc).__name__} tools={','.join(last_tools) or '-'} "
            f"detail={detail}"
        )
        sv.logger.debug(
            f"AI 请求失败 traceback provider={provider_id} scope={scope_key} "
            f"conv={conv.name}\n{traceback.format_exc()}"
        )
        await send_to_event(
            bot, event, f"AI 请求失败（{type(exc).__name__}），请稍后再试。"
        )
        return
    if result is None:
        return

    agent_deps.telemetry.record_success(result)
    # all_messages() = 传入的 history + 本轮新增；只把新增折成事件 append，
    # 避免重复记录历史（pydantic-ai 已验证该前缀对齐语义）。
    new_messages = list(result.all_messages())[len(history) :]
    manager.commit_turn(scope_key, new_messages, provider_id)
    sv.logger.info(
        f"AI 请求成功 provider={provider_id} scope={scope_key} "
        f"conv={conv.name} tokens={metrics.snapshot_from_result(result).total_tokens}"
    )

    raw = result.output
    mask = await _image_input_mask(bot, event)
    if mask:
        raw = mask + raw
    await _send_result(bot, event, raw, config, provider_id)


async def _image_input_mask(bot: Bot, event: Event) -> str:
    """含图输入时返回图片输入 mask 文案；无图返回空串。解析失败按无图处理。"""
    try:
        from hoshino.util.media import get_event_media_segments
        from nonebot_plugin_alconna.uniseg import Image as UniImage

        images = await get_event_media_segments(bot, event, UniImage)
    except Exception as exc:
        sv.logger.warning(f"AI 媒体段解析失败 error={type(exc).__name__}")
        images = []
    if images:
        return "（目前还不支持图片输入，请用文字描述图片内容或直接提问。）\n\n"
    return ""


async def _send_result(
    bot: Bot, event: Event, raw: str, config, provider_id: str
) -> None:
    """先渲染 Markdown 为图片，失败回退纯文本。"""
    try:
        png = await asyncio.wait_for(
            rendering.render_markdown(raw, config),
            timeout=config.render_timeout_seconds,
        )
        await send_to_event(bot, event, UniMessage.image(raw=png))
    except Exception as exc:
        sv.logger.warning(
            f"AI 渲染失败 provider={provider_id} error={type(exc).__name__}，回退纯文本"
        )
        await send_to_event(bot, event, raw)
