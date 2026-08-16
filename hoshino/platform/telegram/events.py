"""Telegram events that are not parsed by the pinned adapter release."""

from __future__ import annotations

from typing import override

from nonebot.adapters.telegram.event import NoticeEvent
from nonebot.adapters.telegram.model import MessageReactionUpdated


class MessageReactionEvent(NoticeEvent, MessageReactionUpdated):
    """Normalized Telegram ``message_reaction`` update."""

    @override
    def get_user_id(self) -> str:
        if self.user is not None:
            return str(self.user.id)
        if self.actor_chat is not None:
            return str(self.actor_chat.id)
        raise ValueError("Telegram reaction has no actor")

    @override
    def get_session_id(self) -> str:
        return f"group_{self.chat.id}_{self.get_user_id()}"


__all__ = ["MessageReactionEvent"]
