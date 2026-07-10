"""消息发送 facade — to_unimessage, send_to_event, send_to_target"""

from __future__ import annotations

from typing import Any

from nonebot.adapters import Bot, Event, Message as AdapterMessage
from nonebot_plugin_alconna.uniseg import Target, UniMessage
from nonebot_plugin_alconna.uniseg.constraint import SerializeFailed
from nonebot_plugin_alconna.uniseg.fallback import FallbackStrategy

from hoshino.platform.ob11.message import (
    MessageLike as MessageLike,
    custom_node_segment as custom_node_segment,
    image_segment as image_segment,
    message_from_parts as message_from_parts,
    text_message as text_message,
    video_segment as video_segment,
)
from hoshino.platform.ob11.types import Message
from hoshino.platform.event import get_user_id
from hoshino.platform.telegram.types import Message as TelegramMessage
from hoshino.platform.telegram.types import MessageSegment as TelegramMessageSegment


async def to_unimessage(
    message: MessageLike,
    *,
    bot: Bot | None = None,
    event: Event | None = None,
) -> UniMessage:
    if isinstance(message, UniMessage):
        return message
    if isinstance(message, str):
        return UniMessage.text(message)
    if isinstance(message, AdapterMessage):
        return await UniMessage.generate(message=message, bot=bot, event=event)
    if isinstance(message, TelegramMessageSegment):
        return await UniMessage.generate(
            message=TelegramMessage(message),
            bot=bot,
            event=event,
        )
    return await UniMessage.generate(message=Message(message), bot=bot, event=event)


async def send_to_event(
    bot: Bot,
    event: Event,
    message: MessageLike,
    *,
    at_sender: bool = False,
    fallback: bool | FallbackStrategy = FallbackStrategy.rollback,
    **kwargs: Any,
):
    msg = await to_unimessage(message, bot=bot, event=event)
    user_id = get_user_id(event)
    if at_sender and user_id is not None:
        msg = UniMessage.at(str(user_id)) + UniMessage.text(" ") + msg
    return await msg.send(event, bot=bot, fallback=fallback, **kwargs)


async def send_to_target(
    bot: Bot,
    target: Target,
    message: MessageLike,
    *,
    fallback: bool | FallbackStrategy = FallbackStrategy.rollback,
    **kwargs: Any,
):
    msg = await to_unimessage(message, bot=bot)
    return await msg.send(target, bot=bot, fallback=fallback, **kwargs)


async def send_to_event_or_fallback(
    bot: Bot,
    event: Event,
    message: MessageLike,
    *,
    fallback: bool | FallbackStrategy = FallbackStrategy.rollback,
    **kwargs: Any,
):
    try:
        return await send_to_event(bot, event, message, fallback=fallback, **kwargs)
    except SerializeFailed:
        return await bot.send(event, message, **kwargs)
