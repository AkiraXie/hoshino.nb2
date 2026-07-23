"""Helpers for sending from the current matcher context."""

from __future__ import annotations

from collections.abc import Sequence

from nonebot.adapters import Bot
from nonebot.matcher import current_bot, current_event, current_matcher

from hoshino import hsn_nickname
from hoshino.platform import (
    MessageLike,
    get_group_id,
    get_user_id,
    group_target,
    send_group_forward,
    send_private_forward,
    send_to_event,
    send_to_target,
)


async def send(
    message: MessageLike,
    *,
    call_header: bool = False,
    at_sender: bool = False,
    **kwargs,
) -> None:
    matcher = current_matcher.get()
    if matcher is None:
        raise ValueError("No running matcher found!")
    if isinstance(message, str) and not call_header and not at_sender:
        await matcher.send(
            message,
            call_header=call_header,
            at_sender=at_sender,
            **kwargs,
        )
        return
    bot = current_bot.get()
    event = current_event.get()
    await send_to_event(
        bot,
        event,
        message,
        call_header=call_header,
        at_sender=at_sender,
        **kwargs,
    )


async def send_segments(messages: Sequence[MessageLike]) -> None:
    if not messages:
        return
    if len(messages) == 1:
        await send(messages[0])
        return
    bot = current_bot.get()
    event = current_event.get()
    if (group_id := get_group_id(event)) is not None:
        await send_group_forward(
            bot,
            group_id,
            messages,
            user_id=bot.self_id,
            nickname=hsn_nickname,
        )
    elif (user_id := get_user_id(event)) is not None:
        await send_private_forward(
            bot,
            user_id,
            messages,
            node_user_id=bot.self_id,
            nickname=hsn_nickname,
        )


async def send_group_segments(
    bot: Bot,
    group_id: int,
    messages: Sequence[MessageLike],
) -> None:
    if not messages:
        return
    if len(messages) == 1:
        await send_to_target(bot, group_target(group_id), messages[0])
        return
    await send_group_forward(
        bot,
        group_id,
        messages,
        user_id=bot.self_id,
        nickname=hsn_nickname,
    )


async def finish(
    message: MessageLike | None = None,
    *,
    call_header: bool = False,
    at_sender: bool = False,
    **kwargs,
) -> None:
    matcher = current_matcher.get()
    if matcher is None:
        raise ValueError("No running matcher found!")
    if message is not None:
        await send(
            message,
            call_header=call_header,
            at_sender=at_sender,
            **kwargs,
        )
    await matcher.finish()


__all__ = [
    "finish",
    "send",
    "send_group_segments",
    "send_segments",
]
