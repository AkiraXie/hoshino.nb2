"""AI 聊天插件：以 ``#`` 开头触发对话。

- 群聊/私聊均可用，不要求 @机器人。
- 聊天不携带 provider 参数；provider 由当前 scope 绑定或全局默认解析。
- 模型输出 Markdown 先渲染为图片；渲染失败（超时/浏览器异常）回退纯文本。
- 日志只记录 provider id、scope、耗时、错误类型，不打印 key 或完整历史。
"""

from __future__ import annotations

import asyncio
import time

from nonebot.adapters import Bot, Event
from nonebot_plugin_alconna.uniseg import UniMessage

from hoshino.platform import (
    event_scope_key,
    get_plaintext,
    send_to_event,
)

from . import context, metrics, providers, rendering
from .base import (
    get_config,
    provider_error_message,
    resolve_provider,
    sv,
)
from .persona import resolve_persona
from .store import load_session_messages, save_session_messages

# 默认 block=True，避免 ``#`` 消息继续命中其他 on_message 规则。
chat = sv.on_startswith("#", only_group=False, only_to_me=False)


@chat.handle()
async def _(bot: Bot, event: Event):
    scope_key = event_scope_key(bot, event)
    prompt = get_plaintext(event).removeprefix("#").strip()
    if not prompt:
        return

    config = get_config()
    provider_id = resolve_provider(scope_key, config)
    if provider_id is None:
        await send_to_event(bot, event, provider_error_message(config))
        return

    provider_config = config.get_provider(provider_id)
    if provider_config is None:
        await send_to_event(bot, event, "AI 配置异常：provider 不存在。")
        return

    # 会话历史：读取 → 反序列化 → 按 max_history_messages 裁剪。
    history_json = load_session_messages(scope_key) if scope_key else None
    messages = context.deserialize_messages(history_json)
    history = context.prepare_history(scope_key, messages, config)

    system_prompt = resolve_persona(scope_key, config)
    model_name = provider_config.config.model or provider_id
    agent = providers.build_agent(
        provider_id, provider_config, system_prompt, proxy=config.proxy
    )

    start = time.perf_counter()
    try:
        result = await agent.run(prompt, message_history=history)
    except Exception as exc:
        latency_ms = (time.perf_counter() - start) * 1000
        error_type = type(exc).__name__
        metrics.record_error(
            provider_id=provider_id,
            scope_key=scope_key or "",
            model=model_name,
            latency_ms=latency_ms,
            error=error_type,
        )
        sv.logger.warning(
            f"AI 请求失败 provider={provider_id} scope={scope_key} error={error_type}"
        )
        await send_to_event(bot, event, f"AI 请求失败（{error_type}），请稍后再试。")
        return

    latency_ms = (time.perf_counter() - start) * 1000
    snapshot = metrics.snapshot_from_result(result)
    metrics.record_success(
        provider_id=provider_id,
        scope_key=scope_key or "",
        model=model_name,
        snapshot=snapshot,
        latency_ms=latency_ms,
    )
    if scope_key:
        save_session_messages(
            scope_key,
            context.serialize_messages(list(result.all_messages())),
            provider_id,
        )
    sv.logger.info(
        f"AI 请求成功 provider={provider_id} scope={scope_key} "
        f"latency={latency_ms:.0f}ms tokens={snapshot.total_tokens}"
    )

    raw = result.data
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
