"""Milky reaction normalization and referenced-message retrieval."""

from __future__ import annotations

from nonebot_plugin_alconna.uniseg import UniMessage

from hoshino.platform.milky.types import (
    Adapter,
    Bot,
    GroupMessageReactionEvent,
)
from hoshino.platform.models import ReactionInfo, RetrievedMessage
from hoshino.platform.superuser import is_superuser


def get_reaction_info(event: object) -> ReactionInfo | None:
    if not isinstance(event, GroupMessageReactionEvent):
        return None
    data = event.data
    return ReactionInfo(
        face_id=str(data.face_id),
        is_add=bool(data.is_add),
        message_id=int(data.message_seq),
        group_id=int(data.group_id),
        user_id=int(data.user_id),
        reaction_type=data.reaction_type,
    )


async def get_reacted_message(
    bot: Bot,
    reaction: ReactionInfo,
) -> RetrievedMessage:
    response = await bot.get_message(
        message_scene="group",
        peer_id=reaction.group_id,
        message_seq=reaction.message_id,
    )
    message = response.message
    forwarded: list[UniMessage] = []

    for segment in message:
        if segment.type != "forward":
            continue
        forward_id = segment.data.get("forward_id")
        if not forward_id:
            continue
        for forwarded_message in await bot.get_forwarded_messages(
            forward_id=forward_id
        ):
            forwarded.append(
                UniMessage.of(forwarded_message.message, adapter=Adapter.get_name())
            )

    sender_id = str(response.sender_id)
    return RetrievedMessage(
        sender_id=sender_id,
        content=UniMessage.of(message, adapter=Adapter.get_name()),
        forwarded=tuple(forwarded),
        trusted_sender=sender_id == bot.self_id or is_superuser(bot, sender_id),
    )


__all__ = ["get_reacted_message", "get_reaction_info"]
