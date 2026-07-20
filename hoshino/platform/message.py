"""消息发送 facade — to_unimessage, send_to_event, send_to_target"""

from __future__ import annotations

from typing import Any

from nonebot.adapters import Bot, Event
from nonebot.adapters import Message as AdapterMessage
from nonebot_plugin_alconna.uniseg import Target, UniMessage
from nonebot_plugin_alconna.uniseg.constraint import SerializeFailed
from nonebot_plugin_alconna.uniseg.fallback import FallbackStrategy

from hoshino.platform.event import get_user_id
from hoshino.platform.milky.types import Message as MilkyMessage
from hoshino.platform.milky.types import MessageSegment as MilkyMessageSegment
from hoshino.platform.ob11.message import MessageLike as MessageLike
from hoshino.platform.ob11.message import custom_node_segment as custom_node_segment
from hoshino.platform.ob11.message import image_segment as image_segment
from hoshino.platform.ob11.message import message_from_parts as message_from_parts
from hoshino.platform.ob11.message import text_message as text_message
from hoshino.platform.ob11.message import video_segment as video_segment
from hoshino.platform.ob11.types import Adapter as OB11Adapter
from hoshino.platform.ob11.types import Message
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
        if event is None:
            return UniMessage.of(message, bot=bot)
        return await UniMessage.generate(message=message, bot=bot, event=event)
    if isinstance(message, TelegramMessageSegment):
        adapter_message = TelegramMessage(message)
        if event is None:
            return UniMessage.of(adapter_message, bot=bot)
        return await UniMessage.generate(
            message=adapter_message,
            bot=bot,
            event=event,
        )
    if isinstance(message, MilkyMessageSegment):
        adapter_message = MilkyMessage(message)
        if event is None:
            return UniMessage.of(adapter_message, bot=bot)
        return await UniMessage.generate(
            message=adapter_message,
            bot=bot,
            event=event,
        )
    adapter_message = Message(message)
    if event is None:
        return UniMessage.of(adapter_message, adapter=OB11Adapter.get_name())
    return await UniMessage.generate(
        message=adapter_message,
        bot=bot,
        event=event,
    )


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
