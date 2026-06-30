from __future__ import annotations

from typing import Any, Union

from nonebot.adapters import Bot, Event, Message as AdapterMessage
from nonebot_plugin_alconna.uniseg import Target, UniMessage
from nonebot_plugin_alconna.uniseg.constraint import SerializeFailed
from nonebot_plugin_alconna.uniseg.fallback import FallbackStrategy

from hoshino.message import Message, MessageSegment
from .event import get_user_id

MessageLike = Union[str, Message, MessageSegment, UniMessage]


def image_segment(file: Any) -> MessageSegment:
    return MessageSegment.image(file)


def video_segment(file: Any) -> MessageSegment:
    return MessageSegment.video(file)


def custom_node_segment(
    *,
    user_id: int,
    nickname: str,
    content: MessageLike,
) -> MessageSegment:
    return MessageSegment.node_custom(
        user_id=user_id,
        nickname=nickname,
        content=content,
    )


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
