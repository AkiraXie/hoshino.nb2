"""OneBot v11 reaction normalization and referenced-message retrieval."""

from __future__ import annotations

from typing import Any

from nonebot.compat import type_validate_python
from nonebot_plugin_alconna.uniseg import UniMessage

from hoshino.platform.models import ReactionInfo, RetrievedMessage
from hoshino.platform.ob11.events import GroupMsgEmojiLikeEvent, GroupReactionEvent
from hoshino.platform.ob11.types import Adapter, Bot, Event, Message
from hoshino.platform.superuser import is_superuser


def get_reaction_info(event: Event) -> ReactionInfo | None:
    """Map supported OB11 extension events to the common reaction model."""

    if isinstance(event, GroupReactionEvent):
        return ReactionInfo(
            face_id=str(event.code),
            is_add=event.sub_type == "add",
            message_id=int(event.message_id),
            group_id=int(event.group_id),
            user_id=int(event.operator_id),
            reaction_type="face",
        )
    if isinstance(event, GroupMsgEmojiLikeEvent) and event.likes:
        return ReactionInfo(
            face_id=str(event.likes[0].emoji_id),
            # LLOneBot reports the current like collection rather than a
            # separate add/remove action.  A present like is therefore an add.
            is_add=True,
            message_id=int(event.message_id),
            group_id=int(event.group_id),
            user_id=int(event.user_id),
            reaction_type="emoji",
        )
    return None


def _message(value: Any) -> Message:
    if isinstance(value, Message):
        return value
    return type_validate_python(Message, value)


def _forward_content(node: Any) -> Any:
    if not isinstance(node, dict):
        return node
    if content := node.get("content"):
        return content
    data = node.get("data")
    if isinstance(data, dict):
        return data.get("content")
    return None


async def get_reacted_message(
    bot: Bot,
    reaction: ReactionInfo,
) -> RetrievedMessage:
    """Fetch and normalize the OB11 message referenced by a reaction."""

    response = await bot.get_msg(message_id=reaction.message_id)
    sender_id = str(response.get("sender", {}).get("user_id", ""))
    message = _message(response.get("message", []))
    forwarded: list[UniMessage] = []

    for segment in message:
        if segment.type != "forward" or not (forward_id := segment.data.get("id")):
            continue
        forward = await bot.get_forward_msg(id=forward_id)
        nodes = forward.get("messages") or forward.get("message") or []
        forwarded.extend(
            UniMessage.of(_message(content), adapter=Adapter.get_name())
            for node in nodes
            if (content := _forward_content(node))
        )

    return RetrievedMessage(
        sender_id=sender_id,
        content=UniMessage.of(message, adapter=Adapter.get_name()),
        forwarded=tuple(forwarded),
        trusted_sender=sender_id == bot.self_id or is_superuser(bot, sender_id),
    )
