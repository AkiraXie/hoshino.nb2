"""AI 聊天插件：以 ``#`` 开头触发对话，支持每 scope 多对话（上下文）管理。

- 群聊/私聊均可用，不要求 @机器人；只感知 ``#`` 前缀消息。
- ``#`` 命名空间保留词为控制命令（整词精确匹配）：
  ``#new [name]`` 新建并切换 / ``#switch|sw <name>`` 切换 / ``#list|ls`` 列出 /
  ``#clear`` 清空当前对话 / ``#goal ...`` 查看与管理跨轮目标；其余内容一律按聊天
  处理（``#new 特性介绍`` 是提问）。
- 上下文（Session→Conversation，对齐 AstrBot）：内存缓存 + SQLite write-through，
  见 ``sessions.py``；轮次按 scope 锁串行化，run 进行中再收 ``#`` 回忙提示。
- 执行护栏（持久化不替代超时，见 aichat-context-timeout-plan.md §3）：
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
)
from hoshino.ai.base import (
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
    provider_id = resolve_provider(scope_key, config)
    if provider_id is None:
        await send_to_event(bot, event, provider_error_message(config))
        return
    record = provider.get_provider(provider_id)
    if record is None:
        await send_to_event(bot, event, "AI 配置异常：provider 不存在。")
        return
    text_model, vision_model = provider.resolve_models(scope_key, provider_id)

    # 多模态选择：事件含图且 scope/provider 配了多模态模型 → vision 模型 + 图片内容；
    # 否则 text 模型（含图但无 vision 时保留 mask 提示，见 _send_result）。
    images = await _event_images(bot, event)
    use_vision = bool(images and vision_model)
    model_name = vision_model if use_vision else text_model
    if not model_name:
        await send_to_event(
            bot, event, f"provider `{provider_id}` 未配置文本模型，请联系管理员。"
        )
        return

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

    # 多模态输入：文本 + 图片内容（ImageUrl / BinaryContent）；无图或全失败回退纯文本。
    prompt_arg: str | list = prompt
    if use_vision:
        prompt_arg = ai_media.build_multimodal_prompt(prompt, images)

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

    try:
        result = await asyncio.wait_for(
            runner.run_agent_with_retry(
                agent,
                prompt_arg,
                deps=agent_deps,
                message_history=history,
                usage_limits=UsageLimits(request_limit=config.chat_max_requests),
                run_log=run_log,
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
    sv.logger.info(
        f"AI 请求成功 provider={provider_id} scope={scope_key} "
        f"conv={conv.name} tokens={metrics.snapshot_from_result(result).total_tokens}"
    )

    raw = result.output
    if images and not use_vision:
        # 含图但当前没有多模态模型：回复开头提示本次未看图。
        raw = "（目前未启用多模态模型，请用文字描述图片内容或直接提问。）\n\n" + raw
    await _send_result(bot, event, raw, config, provider_id)


async def _event_images(bot: Bot, event: Event) -> list:
    """提取事件中的图片段（含回复引用/转发）；解析失败按无图处理。"""
    try:
        from hoshino.util.media import get_event_media_segments
        from nonebot_plugin_alconna.uniseg import Image as UniImage

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
