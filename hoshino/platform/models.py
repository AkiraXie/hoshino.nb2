"""Adapter-neutral values shared by platform dependencies.

The application layer should consume these small records instead of importing
an adapter's event or message classes.  Adapter-specific parsing lives under
``hoshino.platform.<adapter>``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from nonebot_plugin_alconna.uniseg import UniMessage


@dataclass(frozen=True, slots=True)
class ReactionInfo:
    """Normalized group-message reaction metadata."""

    face_id: str
    is_add: bool
    message_id: int
    group_id: int
    user_id: int
    reaction_type: Literal["face", "emoji"]


@dataclass(frozen=True, slots=True)
class RetrievedMessage:
    """A platform-neutral view of a message referenced by a reaction."""

    sender_id: str
    content: UniMessage
    forwarded: tuple[UniMessage, ...] = field(default_factory=tuple)
    trusted_sender: bool = False

    @property
    def messages(self) -> tuple[UniMessage, ...]:
        """Return the original message followed by expanded forward nodes."""

        return (self.content, *self.forwarded)
