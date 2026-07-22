"""Telegram reaction normalization."""

from __future__ import annotations

from hoshino.platform.models import ReactionInfo
from hoshino.platform.telegram.events import MessageReactionEvent


def _reaction_id(value: object) -> str:
    reaction_type = getattr(value, "type", "")
    if reaction_type == "emoji":
        return str(getattr(value, "emoji", ""))
    if reaction_type == "custom_emoji":
        return f"custom:{getattr(value, 'custom_emoji_id', '')}"
    return str(reaction_type)


def get_reaction_info(event: MessageReactionEvent) -> ReactionInfo | None:
    old = [_reaction_id(item) for item in event.old_reaction]
    new = [_reaction_id(item) for item in event.new_reaction]
    additions = [value for value in new if value not in old]
    removals = [value for value in old if value not in new]
    if additions:
        face_id, is_add = additions[0], True
    elif removals:
        face_id, is_add = removals[0], False
    else:
        return None

    user_id = event.user.id if event.user is not None else event.actor_chat.id
    return ReactionInfo(
        face_id=face_id,
        is_add=is_add,
        message_id=int(event.message_id),
        group_id=int(event.chat.id),
        user_id=int(user_id),
        reaction_type="emoji",
    )


__all__ = ["get_reaction_info"]
