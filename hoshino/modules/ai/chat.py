"""AI 聊天插件：``@机器人`` 或 ``#`` 前缀触发对话，支持多对话（上下文）管理。

- 群聊/私聊均可用。触发条件：
  - @本机器人（to_me）→ 一定触发，不要求 ``#`` 前缀；
  - 不 at 任何人 + ``#`` 前缀消息 → 触发（``#`` 命名空间保留词为控制命令，
    整词精确匹配：``#new [name]`` / ``#switch|sw <name>`` / ``#list|ls`` /
    ``#clear`` / ``#goal ...``；其余内容一律按聊天处理）；
  - 回复消息 + 不 at 任何人 + ``#`` 前缀 → 触发（回复本身不额外放行，仍需 ``#``）。
- 引用识别：触发后会把回复指向的内容一并交给模型——聊天记录文字、转发消息文字、
  回复/转发里的图片（原生多模态），而不仅是当前消息本体。
- 上下文（Session→Conversation，对齐 AstrBot）：内存缓存 + SQLite write-through，
  见 ``sessions.py``；轮次按 scope 锁串行化，run 进行中再收消息回忙提示。
- 执行护栏（持久化不替代超时）：
  run 墙钟 ``chat_run_timeout_seconds`` + ``UsageLimits(chat_max_requests)``。
  超时/超限把本轮提问写入上下文可续问；provider 异常不写。
- 模型输出 Markdown 先渲染为图片；渲染失败（超时/浏览器异常）回退纯文本。
- 含图消息：同一 model 一次吃压缩后的 BinaryContent + 真实 prompt（原生多模态）；
  未配置 model 时提示超级用户 ``ai model default``。
- 日志只记录 provider id、scope、耗时、错误类型，不打印 key 或完整历史。
"""

from __future__ import annotations

import asyncio
import contextlib
import time
import traceback
from collections.abc import Callable

from nonebot.adapters import Bot, Event
from nonebot.rule import Rule
from nonebot_plugin_alconna.uniseg import Image as UniImage
from nonebot_plugin_alconna.uniseg import UniMessage
from pydantic_ai.exceptions import UsageLimitExceeded
from pydantic_ai.usage import UsageLimits

from hoshino.ai import (
    context,
    deps,
    errors,
    goal,
    hooks,
    metrics,
    provider,
    providers,
    rendering,
    runner,
    sessions,
)
from hoshino.ai import (
    media as ai_media,
)
from hoshino.ai.base import get_config
from hoshino.core.service import Service
from hoshino.platform import (
    event_scope_key,
    get_event_message,
    get_forwarded_messages,
    get_group_id,
    get_plaintext,
    get_reply_content,
    send_to_event,
    to_unimessage,
)
from hoshino.util.media import get_event_media_segments

# aichat 服务仅属于聊天插件（# 触发）：默认关闭，按 scope 启用后才应答。
sv = Service("aichat", enable_on_default=False, visible=False)


async def _ai_chat_rule(bot: Bot, event: Event) -> bool:
    if event.is_tome():
        return get_plaintext(event).lstrip().startswith("#")
    msg = get_event_message(event)
    unimsg = (
        await to_unimessage(msg, bot=bot, event=event, attach_reply=False)
        if msg is not None
        else None
    )
    return unimsg and unimsg.startswith("#")


# 默认 block=True，避免命中消息继续落到其他 on_message 规则。
chat = sv.on_message(
    rule=Rule(_ai_chat_rule),
    only_group=False,
    only_to_me=False,
    priority=10,
    block=True,
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

    lock = sessions.conversation_manager.turn_lock(scope_key)
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
    if head == "goal":
        if not rest:
            return ("goal_view", None)
        sub = rest[0].lower()
        if sub == "set":
            return ("goal_set", " ".join(rest[1:]) if len(rest) > 1 else None)
        if sub in ("pause", "resume", "done", "clear") and len(rest) == 1:
            return (f"goal_{sub}", None)
        return ("goal_help", None)
    return None


async def _handle_control(
    bot: Bot, event: Event, scope_key: str, control: tuple[str, str | None]
) -> None:
    manager = sessions.conversation_manager
    action, arg = control

    if action.startswith("goal_"):
        await _handle_goal(bot, event, scope_key, action, arg)
        return

    match action:
        case "new":
            try:
                conv = manager.create(scope_key, arg)
            except ValueError as exc:
                await send_to_event(bot, event, str(exc))
                return
            await send_to_event(bot, event, f"已新建并切换到对话 `{conv.name}`。")
        case "switch":
            conv = manager.switch(scope_key, arg or "")
            if conv is None:
                names = "、".join(s["name"] for s in manager.list_summaries(scope_key))
                await send_to_event(bot, event, f"对话 `{arg}` 不存在。可用：{names or '（无）'}")
                return
            await send_to_event(bot, event, f"已切换到对话 `{conv.name}`。")
        case "list":
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
        case "clear":
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


# ---------------------------------------------------------------- 目标（goal）


_GOAL_PHASE_LABEL = {
    "active": "进行中",
    "paused": "已暂停",
    "blocked": "已阻塞",
    "complete": "已完成",
}

_GOAL_TRANSITION = {
    "goal_pause": "pause",
    "goal_resume": "resume",
    "goal_done": "complete",
}


def _format_goal(g) -> str:
    phase = _GOAL_PHASE_LABEL.get(g.phase, g.phase)
    rounds = f"{g.completed_rounds}/{g.max_rounds}" if g.max_rounds else str(g.completed_rounds)
    lines = [f"目标（{phase}）：{g.objective}", f"轮次：{rounds}"]
    if g.blocked_reason:
        lines.append(f"阻塞原因：{g.blocked_reason}")
    return "\n".join(lines)


async def _handle_goal(
    bot: Bot, event: Event, scope_key: str, action: str, arg: str | None
) -> None:
    service = goal.GoalService()

    match action:
        case "goal_view":
            current = service.get(scope_key)
            if current is None:
                await send_to_event(bot, event, "当前没有目标，用 `#goal set <目标>` 创建一个。")
            else:
                await send_to_event(bot, event, _format_goal(current))
        case "goal_set":
            if not arg:
                await send_to_event(bot, event, "用法：`#goal set <目标>`。")
                return
            try:
                created = service.create(scope_key, arg)
            except ValueError as exc:
                await send_to_event(bot, event, str(exc))
                return
            await send_to_event(bot, event, f"已设定目标：{created.objective}")
        case "goal_clear":
            if not await _can_clear(bot, event):
                await send_to_event(bot, event, "清除目标需要管理员权限。")
                return
            await send_to_event(
                bot, event, "已清除目标。" if service.clear(scope_key) else "当前没有目标。"
            )
        case _:
            transition = _GOAL_TRANSITION.get(action)
            if transition is not None:
                await _goal_transition(bot, event, scope_key, transition)
                return
            # goal_help / 非法子命令
            await send_to_event(
                bot,
                event,
                "用法：`#goal` 查看 / `#goal set <目标>` 设定 / `#goal pause|resume|done` / "
                "`#goal clear`。",
            )


async def _goal_transition(bot: Bot, event: Event, scope_key: str, action: str) -> None:
    service = goal.GoalService()
    current = service.get(scope_key)
    if current is None:
        await send_to_event(bot, event, "当前没有目标，用 `#goal set <目标>` 创建一个。")
        return
    try:
        updated = service.update(scope_key, goal.GoalRef(scope_key, current.revision), action)
    except (goal.GoalConflict, ValueError) as exc:
        await send_to_event(bot, event, str(exc))
        return
    await send_to_event(bot, event, _format_goal(updated))


# ---------------------------------------------------------------- 聊天


async def _handle_chat_turn(bot: Bot, event: Event, scope_key: str, prompt: str):
    """单轮聊天：解析统一 model → 读当前对话上下文 → run（带护栏）→ 渲染回复。"""
    manager = sessions.conversation_manager
    config = get_config()
    # 引用内容注入：回复指向的聊天记录/转发文字一并交给模型理解（图片走多模态）。
    reply_ctx = await _reply_context_text(bot, event)
    if reply_ctx:
        prompt = f"{reply_ctx}\n\n{prompt}"
    provider_id, model_name = provider.resolve_model(scope_key)
    if not provider_id or not model_name:
        await send_to_event(bot, event, "未配置模型，请超级用户 `ai model default`。")
        return
    record = provider.get_provider(provider_id)
    if record is None:
        await send_to_event(bot, event, "AI 配置异常：provider 不存在。")
        return

    # 原生多模态：事件图压缩为 BinaryContent，与真实 prompt 同请求送给同一 model。
    images = await _event_images(bot, event)
    image_parts: list = []
    if images:
        image_parts = await ai_media.image_segments_to_content_async(
            images,
            verify_ssl=config.web_fetch_verify_ssl,
            proxy=provider.resolve_tool_proxy(config.proxy, tool_use_proxy=config.tool_use_proxy),
        )

    conv = manager.get_active(scope_key)
    history = context.prepare_history(scope_key, conv.messages, config, new_question=prompt)

    permissions = await deps.build_permission_snapshot(bot, event)
    agent_deps = deps.construct_chat_deps(
        bot,
        event,
        config,
        permissions,
        provider_id=provider_id,
        model=model_name,
    )
    # pre-step 瀑布：reject（拒绝本轮，不跑模型）/ rewrite（改写模型可见 prompt）。
    # rewrite 只改进入模型的文本；图片 parts 在 rewrite 后再拼，避免钩子丢图。
    pre = hooks.run_pre_step_hooks(
        hooks.PreStepContext(
            prompt=prompt,
            history=history,
            scope_key=scope_key,
            provider_id=provider_id,
            surface="chat",
            deps=agent_deps,
        )
    )
    if pre.action == "reject":
        agent_deps.telemetry.record_error("pre_step_reject")
        await send_to_event(bot, event, pre.reply or "本次请求已被拦截。")
        return
    if pre.action == "rewrite" and pre.prompt is not None:
        prompt = pre.prompt

    prompt_arg = ai_media.build_image_prompt(prompt, image_parts)

    agent = providers.build_agent(
        provider_id,
        record,
        model_name,
        proxy=provider.resolve_effective_proxy(record, config.proxy),
        tool_max_retries=config.tool_max_retries,
    )
    # 失败可观测性：RunLog 记录本轮发起过的工具调用（含超时前），异常时随日志
    # 输出定位是模型侧问题还是工具侧问题（如 web_search）。
    run_log = runner.RunLog()
    stream_logger = _make_stream_logger(provider_id, scope_key, conv.name, model_name)

    try:
        result = await asyncio.wait_for(
            runner.run_agent_with_retry(
                agent,
                prompt_arg,
                deps=agent_deps,
                message_history=history,
                usage_limits=UsageLimits(request_limit=config.chat_max_requests),
                run_log=run_log,
                on_event=stream_logger,
            ),
            timeout=config.chat_run_timeout_seconds,
        )
    except (TimeoutError, UsageLimitExceeded) as exc:
        # 护栏触发：丢弃本次执行，不写入上下文（避免失败的提问/中间产物污染历史）。
        agent_deps.telemetry.record_error(type(exc).__name__)
        run_log.reason = "timeout" if isinstance(exc, TimeoutError) else "max-requests"
        reason = "超时" if isinstance(exc, TimeoutError) else "超出步数限制"
        sv.logger.warning(
            f"AI 请求{reason} provider={provider_id} scope={scope_key} conv={conv.name}"
        )
        await send_to_event(
            bot,
            event,
            f"处理{reason}，本次对话未记录，请重新提问。",
        )
        return
    except Exception as exc:
        # 完整错误详情（message + body/status/tool）+ 失败前工具调用；
        # traceback 只在 DEBUG 级别落，避免 WARNING 刷屏。
        run_log.reason = "error"
        detail = errors.format_exception_detail(exc)
        agent_deps.telemetry.record_error(detail)
        tools = ",".join(c["name"] for c in run_log.tool_calls) or "-"
        sv.logger.warning(
            f"AI 请求失败 provider={provider_id} scope={scope_key} conv={conv.name} "
            f"model={model_name} error={type(exc).__name__} tools={tools} "
            f"detail={detail}"
        )
        sv.logger.debug(
            f"AI 请求失败 traceback provider={provider_id} scope={scope_key} "
            f"conv={conv.name}\n{traceback.format_exc()}"
        )
        await send_to_event(bot, event, f"AI 请求失败（{type(exc).__name__}），请稍后再试。")
        return
    if result is None:
        return

    agent_deps.telemetry.record_success(result)
    # 只把本 run 产生的消息折成事件 append。runner 可能在 run 内软压缩临时历史，
    # 因此不能再按进入时 history 的长度手工切片。
    new_messages = runner.result_new_messages(result, history)
    manager.commit_turn(scope_key, new_messages, provider_id, run_log)
    elapsed = run_log.ended_at - run_log.started_at
    usage = metrics.snapshot_from_result(result)
    hit = metrics.cache_hit_ratio(usage.request_tokens, usage.cache_read_tokens)
    sv.logger.info(
        f"AI 请求成功 provider={provider_id} scope={scope_key} "
        f"conv={conv.name} model={model_name} steps={run_log.steps} "
        f"tokens={usage.total_tokens}（in {usage.request_tokens} / "
        f"out {usage.response_tokens} / 缓存读 {usage.cache_read_tokens} / "
        f"写 {usage.cache_write_tokens} / 命中率 {hit:.1%}）耗时={elapsed:.1f}s"
    )

    raw = result.output
    # 结尾总结行确定性兜底（prompt 层已禁用，模型偶发用「一句话版本：」等变体收尾）。
    raw = rendering.strip_trailing_summary(raw)
    sv.logger.info(
        f"AI 回复 provider={provider_id} scope={scope_key} conv={conv.name} "
        f"model={model_name} 字数={len(raw)} "
        f"摘要「{_log_safe(runner.summarize_content(raw, 120))}」"
    )
    await _send_result(bot, event, raw, config, provider_id)


def _log_safe(text: str) -> str:
    """转义 loguru 颜色标签语法（``<tag>``），避免日志内容被误解析为颜色指令。

    工具参数摘要（如 ``{q=<14>}``）与网页/模型文本摘要都可能含尖括号，不转义
    会在 colorize 时抛 ``ValueError`` 中断整条日志链。
    """
    return text.replace("<", "\\<")


def _make_stream_logger(
    provider_id: str, scope_key: str, conv_name: str, model_name: str
) -> Callable[[runner.RunEvent], None]:
    """构造实时日志回调：每个模型请求/工具调用节点即时打印，不再攒到最后。

    供 ``run_agent_with_retry(on_event=...)`` 使用；每行带相对上一节点的耗时。
    思考/中间文本（introspection）不落日志（原始设计也不落）。
    """
    prev = time.time()

    def on_event(ev: runner.RunEvent) -> None:
        nonlocal prev
        now = time.time()
        delta = now - prev
        prev = now
        desc = runner.describe_node(ev.node, ev.ctx)
        if desc is None:
            return
        suffix = f" · {delta:.1f}s" if delta >= 0.05 else ""
        sv.logger.info(
            f"AI 实时 provider={provider_id} scope={scope_key} conv={conv_name} "
            f"model={model_name} {_log_safe(desc)}{suffix}"
        )

    return on_event


def _message_text(message) -> str:
    """提取消息对象的纯文本（duck-typed：优先 extract_plain_text）。"""
    extract = getattr(message, "extract_plain_text", None)
    if callable(extract):
        with contextlib.suppress(Exception):
            return str(extract())
    return str(message)


async def _reply_context_text(bot: Bot, event: Event) -> str:
    """收集引用内容的文本：回复目标（含 OB11 经 get_msg 拉取）+ 转发消息。

    图片类引用由 ``_event_images`` 走多模态路径，这里只取文字部分。
    """
    parts: list[str] = []
    reply = await get_reply_content(bot, event)
    if reply is not None:
        text = _message_text(reply)
        if text:
            parts.append(f"用户引用了上一条消息：{text}")
    for msg in await get_forwarded_messages(bot, event):
        text = _message_text(msg)
        if text:
            parts.append(f"转发消息：{text}")
    return "\n".join(parts)


async def _event_images(bot: Bot, event: Event) -> list:
    """提取事件中的图片段（含回复引用/转发）；解析失败按无图处理。"""
    try:
        return await get_event_media_segments(bot, event, UniImage)
    except Exception as exc:
        sv.logger.warning(f"AI 媒体段解析失败 error={type(exc).__name__}")
        return []


async def _send_result(bot: Bot, event: Event, raw: str, config, provider_id: str) -> None:
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
