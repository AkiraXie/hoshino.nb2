"""消息发送 facade — to_unimessage, send_to_event, send_to_target"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from typing import Any

from nonebot.adapters import Bot, Event
from nonebot.adapters import Message as AdapterMessage
from nonebot.adapters import MessageSegment as AdapterMessageSegment
from nonebot.log import logger
from nonebot_plugin_alconna.uniseg import CustomNode, Target, UniMessage
from nonebot_plugin_alconna.uniseg.constraint import SerializeFailed
from nonebot_plugin_alconna.uniseg.fallback import FallbackStrategy
from nonebot_plugin_uninfo import get_session

from hoshino.platform.event import get_group_id, get_user_id
from hoshino.platform.milky.types import Adapter as MilkyAdapter
from hoshino.platform.milky.types import Message as MilkyMessage
from hoshino.platform.milky.types import MessageSegment as MilkyMessageSegment
from hoshino.platform.ob11.message import MessageLike as MessageLike
from hoshino.platform.ob11.message import custom_node_segment as custom_node_segment
from hoshino.platform.ob11.message import image_segment as image_segment
from hoshino.platform.ob11.message import message_from_parts as message_from_parts
from hoshino.platform.ob11.message import text_message as text_message
from hoshino.platform.ob11.message import video_segment as video_segment
from hoshino.platform.ob11.types import Adapter as OB11Adapter
from hoshino.platform.ob11.types import Message as OB11Message
from hoshino.platform.ob11.types import MessageSegment as OB11MessageSegment
from hoshino.platform.superuser import superuser_ids_for_bot
from hoshino.platform.target import private_target
from hoshino.platform.telegram.types import Adapter as TelegramAdapter
from hoshino.platform.telegram.types import Bot as TelegramBot
from hoshino.platform.telegram.types import Message as TelegramMessage
from hoshino.platform.telegram.types import MessageSegment as TelegramMessageSegment

# 无法识别会话发起者时的占位用户 ID（OB11 匿名/系统账号）。
UNKNOWN_USER_ID = 80000000
# 占位用户 ID 对应的引用头。
UNKNOWN_USER_HEADER = ">???\n"


def call_header_from_names(names: Sequence[str | None]) -> str:
    """取第一个非空显示名生成引用头（``>名称\\n``）；全部为空返回空串。"""
    for name in names:
        if name:
            return f">{name}\n"
    return ""


async def to_unimessage(
    message: MessageLike,
    *,
    bot: Bot | None = None,
    event: Event | None = None,
    attach_reply: bool = True,
) -> UniMessage:
    """Convert an outgoing value using its source adapter's message builder."""

    if isinstance(message, UniMessage):
        return message
    if isinstance(message, str):
        return UniMessage.text(message)
    if isinstance(message, MilkyMessage):
        converted = UniMessage.of(message, adapter=MilkyAdapter.get_name())
    elif isinstance(message, TelegramMessage):
        converted = UniMessage.of(message, adapter=TelegramAdapter.get_name())
    elif isinstance(message, OB11Message):
        converted = UniMessage.of(message, adapter=OB11Adapter.get_name())
    elif isinstance(message, MilkyMessageSegment):
        converted = UniMessage.of(
            MilkyMessage(message),
            adapter=MilkyAdapter.get_name(),
        )
    elif isinstance(message, TelegramMessageSegment):
        converted = UniMessage.of(
            TelegramMessage(message),
            adapter=TelegramAdapter.get_name(),
        )
    elif isinstance(message, OB11MessageSegment):
        converted = UniMessage.of(
            OB11Message(message),
            adapter=OB11Adapter.get_name(),
        )
    elif isinstance(message, AdapterMessage):
        converted = UniMessage.of(message, bot=bot)
    else:
        converted = UniMessage.of(
            OB11Message(message),
            adapter=OB11Adapter.get_name(),
        )
    if event is not None and attach_reply:
        await converted.attach_reply(event, bot)
    return converted


async def _call_header(bot: Bot, event: Event) -> str:
    if get_group_id(event) is None or (user_id := get_user_id(event)) is None:
        return ""
    if user_id == UNKNOWN_USER_ID:
        return UNKNOWN_USER_HEADER
    try:
        session = await get_session(bot, event)
    except Exception as error:
        logger.warning("Unable to resolve call header via Uninfo: {}", error)
        return ""
    if session is None:
        return ""
    return call_header_from_names(
        (
            session.member.nick if session.member else None,
            session.user.nick,
            session.user.name,
        )
    )


async def send_to_event(
    bot: Bot,
    event: Event,
    message: MessageLike,
    *,
    at_sender: bool = False,
    call_header: bool = False,
    fallback: bool | FallbackStrategy = FallbackStrategy.rollback,
    **kwargs: Any,
):
    msg = await to_unimessage(message, bot=bot, event=event)
    user_id = get_user_id(event)
    if at_sender and user_id is not None:
        msg = UniMessage.at(str(user_id)) + UniMessage.text(" ") + msg
    if call_header and (header := await _call_header(bot, event)):
        msg = UniMessage.text(header) + msg
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


def _forward_items(messages: Sequence[Any]) -> list[Any]:
    if (
        isinstance(messages, OB11Message)
        and messages
        and all(segment.type == "node" for segment in messages)
    ):
        return list(messages)
    if isinstance(
        messages,
        str | UniMessage | AdapterMessage | AdapterMessageSegment,
    ):
        return [messages]
    return list(messages)


async def _forward_node(
    item: Any,
    *,
    bot: Bot,
    default_user_id: str,
    default_name: str,
) -> tuple[CustomNode, UniMessage]:
    if isinstance(item, CustomNode):
        if isinstance(item.content, UniMessage):
            content = item.content
        elif isinstance(item.content, str):
            content = UniMessage.text(item.content)
        else:
            content = UniMessage(item.content)
        return (
            CustomNode(
                uid=item.uid,
                name=item.name,
                content=content,
                time=item.time,
                context=item.context,
            ),
            content,
        )
    if isinstance(item, OB11MessageSegment) and item.type == "node":
        data = item.data
        content = await to_unimessage(
            OB11Message(data.get("content", [])),
            bot=bot,
        )
        return (
            CustomNode(
                uid=str(data.get("user_id", default_user_id)),
                name=str(data.get("nickname") or data.get("name") or default_name),
                content=content,
            ),
            content,
        )
    content = await to_unimessage(item, bot=bot)
    return (
        CustomNode(
            uid=default_user_id,
            name=default_name,
            content=content,
        ),
        content,
    )


async def send_forward_to_target(
    bot: Bot,
    target: Target,
    messages: Sequence[Any],
    *,
    user_id: int | str | None = None,
    nickname: str | None = None,
    fallback: bool | FallbackStrategy = FallbackStrategy.rollback,
    sequential_delay: float = 0.3,
) -> list[Any]:
    """Send native constructed forwards, with sequential Telegram fallback."""

    items = _forward_items(messages)
    if not items:
        raise ValueError("Forward messages cannot be empty")
    default_user_id = str(user_id if user_id is not None else bot.self_id)
    default_name = nickname or str(bot.self_id)
    nodes: list[CustomNode] = []
    contents: list[UniMessage] = []
    for item in items:
        node, content = await _forward_node(
            item,
            bot=bot,
            default_user_id=default_user_id,
            default_name=default_name,
        )
        nodes.append(node)
        contents.append(content)

    if isinstance(bot, TelegramBot):
        receipts = []
        for index, content in enumerate(contents):
            receipts.append(
                await send_to_target(
                    bot,
                    target,
                    content,
                    fallback=fallback,
                )
            )
            if sequential_delay and index < len(contents) - 1:
                await asyncio.sleep(sequential_delay)
        return receipts

    receipt = await send_to_target(
        bot,
        target,
        UniMessage.reference(*nodes),
        fallback=fallback,
    )
    return [receipt]


async def send_to_event_or_fallback(
    bot: Bot,
    event: Event,
    message: MessageLike,
    *,
    at_sender: bool = False,
    call_header: bool = False,
    fallback: bool | FallbackStrategy = FallbackStrategy.rollback,
    **kwargs: Any,
):
    try:
        return await send_to_event(
            bot,
            event,
            message,
            at_sender=at_sender,
            call_header=call_header,
            fallback=fallback,
            **kwargs,
        )
    except SerializeFailed:
        return await bot.send(event, message, **kwargs)


async def send_to_superuser(bot: Bot, message: MessageLike = "") -> None:
    """Send a private message to every superuser configured for ``bot``."""
    for superuser in superuser_ids_for_bot(bot):
        await asyncio.sleep(0.5)
        await send_to_target(bot, private_target(superuser), message)
