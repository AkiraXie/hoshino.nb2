"""AI 聊天插件：``#`` 前缀或回复 bot 自己的消息触发对话，支持多对话（上下文）管理。

- 群聊/私聊均可用，不要求 @机器人。触发条件：
  - ``#`` 前缀消息（``#`` 命名空间保留词为控制命令，整词精确匹配：
    ``#new [name]`` / ``#switch|sw <name>`` / ``#list|ls`` / ``#clear`` /
    ``#goal ...``；其余内容一律按聊天处理）；
  - 对机器人自己消息的引用回复（无需 ``#``，如回复 AI 发的图片消息继续追问）。
- 引用识别：触发后会把回复指向的内容一并交给模型——聊天记录文字、转发消息文字、
  回复/转发里的图片（多模态路径），而不仅是当前消息本体。
- 上下文（Session→Conversation，对齐 AstrBot）：内存缓存 + SQLite write-through，
  见 ``sessions.py``；轮次按 scope 锁串行化，run 进行中再收消息回忙提示。
- 执行护栏（持久化不替代超时）：
  run 墙钟 ``chat_run_timeout_seconds`` + ``UsageLimits(chat_max_requests)``。
  超时/超限把本轮提问写入上下文可续问；provider 异常不写。
- 模型输出 Markdown 先渲染为图片；渲染失败（超时/浏览器异常）回退纯文本。
- 多模态：scope/provider 配置多模态模型时，含图消息走 vision 模型（图片经
  ImageUrl/BinaryContent 传入）；未配置时保留文本提示（mask），模型不看图。
- 日志只记录 provider id、scope、耗时、错误类型，不打印 key 或完整历史。
"""

from __future__ import annotations

import asyncio
import time
import traceback
from collections.abc import Callable

from nonebot.adapters import Bot, Event
from nonebot.rule import Rule
from nonebot_plugin_alconna.uniseg import Image as UniImage
from nonebot_plugin_alconna.uniseg import UniMessage
from pydantic_ai.exceptions import UsageLimitExceeded
from pydantic_ai.usage import UsageLimits

from hoshino.platform import (
    event_scope_key,
    get_event_message,
    get_forwarded_messages,
    get_group_id,
    get_plaintext,
    get_reply_content,
    is_reply_to_bot,
    send_to_event,
    to_unimessage,
)

from hoshino.ai import (
    context,
    deps,
    errors,
    goal,
    hooks,
    media as ai_media,
    metrics,
    provider,
    providers,
    rendering,
    runner,
    sessions,
    vision,
)
from hoshino.ai.base import (
    get_config,
    provider_error_message,
    resolve_provider,
)
from hoshino.core.service import Service
from hoshino.util.media import get_event_media_segments

# aichat 服务仅属于聊天插件（# 触发）：默认关闭，按 scope 启用后才应答。
sv = Service("aichat", enable_on_default=False, visible=False)


async def _ai_chat_rule(bot: Bot, event: Event) -> bool:
    """``#`` 前缀（``#xxx`` / ``@本bot #xxx``），或对机器人自己消息的引用回复。

    按消息段结构判断而非 ``get_plaintext``：纯文本提取会丢弃 at 段，
    导致 ``@bot2 #xxx`` 被误判为 ``#xxx`` 而触发本 bot。
    """
    if await _hash_prefix_trigger(bot, event):
        return True
    return is_reply_to_bot(bot, event)


async def _hash_prefix_trigger(bot: Bot, event: Event) -> bool:
    """``#`` 前缀触发：消息本体以 ``#`` 开头，或 @ 本 bot 后跟 ``#`` 开头文本。

    - ``#xxx`` → True；``@本bot #xxx`` → True（@ 自己后继续检查文本）；
    - ``@其他 #xxx`` → False（at 段目标不是自己，直接拒绝）；
    - 文本段前出现图片等非文本段 → False。
    """
    message = get_event_message(event)
    if message is None:
        return False
    try:
        unimsg = await to_unimessage(message, bot=bot, event=event)
    except Exception:
        return False
    for segment in unimsg:
        if segment.type == "at":
            target = getattr(segment, "target", None)
            if target is not None and str(target) != str(bot.self_id):
                return False  # @ 了其他实体（如另一个 bot）→ 不触发
            continue  # @ 自己 → 继续检查后续文本
        if segment.type == "text":
            return bool(segment.text and segment.text.lstrip().startswith("#"))
        return False  # 文本前出现图片等非文本段 → 不触发
    return False


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


# ---------------------------------------------------------------- 目标（goal）


_GOAL_PHASE_LABEL = {
    "active": "进行中",
    "paused": "已暂停",
    "blocked": "已阻塞",
    "complete": "已完成",
}


def _format_goal(g) -> str:
    phase = _GOAL_PHASE_LABEL.get(g.phase, g.phase)
    rounds = (
        f"{g.completed_rounds}/{g.max_rounds}"
        if g.max_rounds
        else str(g.completed_rounds)
    )
    lines = [f"目标（{phase}）：{g.objective}", f"轮次：{rounds}"]
    if g.blocked_reason:
        lines.append(f"阻塞原因：{g.blocked_reason}")
    return "\n".join(lines)


async def _handle_goal(
    bot: Bot, event: Event, scope_key: str, action: str, arg: str | None
) -> None:
    service = goal.GoalService()

    if action == "goal_view":
        current = service.get(scope_key)
        if current is None:
            await send_to_event(
                bot, event, "当前没有目标，用 `#goal set <目标>` 创建一个。"
            )
        else:
            await send_to_event(bot, event, _format_goal(current))
        return

    if action == "goal_set":
        if not arg:
            await send_to_event(bot, event, "用法：`#goal set <目标>`。")
            return
        try:
            created = service.create(scope_key, arg)
        except ValueError as exc:
            await send_to_event(bot, event, str(exc))
            return
        await send_to_event(bot, event, f"已设定目标：{created.objective}")
        return

    if action == "goal_clear":
        if not await _can_clear(bot, event):
            await send_to_event(bot, event, "清除目标需要管理员权限。")
            return
        await send_to_event(
            bot, event, "已清除目标。" if service.clear(scope_key) else "当前没有目标。"
        )
        return

    transition = {
        "goal_pause": "pause",
        "goal_resume": "resume",
        "goal_done": "complete",
    }.get(action)
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
        await send_to_event(
            bot, event, "当前没有目标，用 `#goal set <目标>` 创建一个。"
        )
        return
    try:
        updated = service.update(
            scope_key, goal.GoalRef(scope_key, current.revision), action
        )
    except (goal.GoalConflict, ValueError) as exc:
        await send_to_event(bot, event, str(exc))
        return
    await send_to_event(bot, event, _format_goal(updated))


# ---------------------------------------------------------------- 聊天


async def _handle_chat_turn(bot: Bot, event: Event, scope_key: str, prompt: str):
    """单轮聊天：解析 provider/双模型 → 读当前对话上下文 → run（带护栏）→ 渲染回复。"""
    manager = sessions.conversation_manager
    config = get_config()
    # 引用内容注入：回复指向的聊天记录/转发文字一并交给模型理解（图片走多模态）。
    reply_ctx = await _reply_context_text(bot, event)
    if reply_ctx:
        prompt = f"{reply_ctx}\n\n{prompt}"
    provider_id = resolve_provider(scope_key, config)
    if provider_id is None:
        await send_to_event(bot, event, provider_error_message(config))
        return
    record = provider.get_provider(provider_id)
    if record is None:
        await send_to_event(bot, event, "AI 配置异常：provider 不存在。")
        return
    text_model, vision_model = provider.resolve_models(scope_key, provider_id)
    if not text_model:
        await send_to_event(
            bot, event, f"provider `{provider_id}` 未配置文本模型，请联系管理员。"
        )
        return

    # 图片识别：vision 模型"看"图产出文字描述 → 交给默认 text 模型作答。
    # 无图或图解析失败时走纯文本；有图但无 vision 模型时保留 mask 提示。
    images = await _event_images(bot, event)
    no_vision_mask = bool(images and not vision_model)
    if images and vision_model:
        image_content = ai_media.image_segments_to_content(images)
        if image_content:
            try:
                description = await vision.describe_images(
                    record, vision_model, image_content, proxy=config.proxy
                )
            except Exception as exc:
                sv.logger.warning(
                    f"AI 图片描述失败 provider={provider_id} error={type(exc).__name__}"
                )
                description = ""
            if description:
                prompt = f"[图片描述]\n{description}\n\n[用户消息]\n{prompt}"
        if not prompt.startswith("[图片描述]"):
            no_vision_mask = True  # 描述失败，退回提示
    model_name = text_model

    conv = manager.get_active(scope_key)
    history = context.prepare_history(scope_key, conv.messages, config)

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
    # rewrite 只改进入模型的文本；事件日志按改写后的内容记录（重放保真优先，
    # 平台聊天记录仍保留用户原话）。本期无默认订阅者。
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

    # 纯文本作答（图片已由 vision 模型转成文字描述注入 prompt）。
    prompt_arg: str = prompt

    agent = providers.build_agent(
        provider_id,
        record,
        model_name,
        proxy=config.proxy,
        web_search_native=config.web_search_native,
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
        # 护栏触发：丢弃本次执行，但把提问留在上下文，下一轮可续问。
        # 已知限制：多模态轮只保留文本 prompt（图片部件不落历史）。
        agent_deps.telemetry.record_error(type(exc).__name__)
        run_log.reason = "timeout" if isinstance(exc, TimeoutError) else "max-requests"
        manager.append_prompt_only(scope_key, prompt, provider_id, run_log)
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
        run_log.reason = "error"
        detail = errors.format_exception_detail(exc)
        agent_deps.telemetry.record_error(detail)
        tools = ",".join(c["name"] for c in run_log.tool_calls) or "-"
        sv.logger.warning(
            f"AI 请求失败 provider={provider_id} scope={scope_key} conv={conv.name} "
            f"error={type(exc).__name__} tools={tools} "
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
    if no_vision_mask:
        # 含图但未配置 vision 模型（或描述失败）：回复开头提示本次未看图。
        raw = (
            "（目前未配置 vision 模型，图片暂无法识别，请用文字描述图片内容。）\n\n"
            + raw
        )
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
        try:
            return str(extract())
        except Exception:
            pass
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
