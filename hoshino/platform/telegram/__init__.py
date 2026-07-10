"""Telegram adapter types and helpers."""

from hoshino.platform.telegram.event import (
    get_chat_id as get_chat_id,
    get_event_message as get_event_message,
    get_group_id as get_group_id,
    get_message_id as get_message_id,
    get_plaintext as get_plaintext,
    get_reply_message as get_reply_message,
    get_session_id as get_session_id,
    get_user_id as get_user_id,
    is_group_event as is_group_event,
    is_message_event as is_message_event,
    is_private_event as is_private_event,
)
from hoshino.platform.telegram.types import (
    Adapter as Adapter,
    Bot as Bot,
    Event as Event,
    Message as Message,
    MessageSegment as MessageSegment,
)

__all__ = [
    "Adapter",
    "Bot",
    "Event",
    "Message",
    "MessageSegment",
    "get_chat_id",
    "get_event_message",
    "get_group_id",
    "get_message_id",
    "get_plaintext",
    "get_reply_message",
    "get_session_id",
    "get_user_id",
    "is_group_event",
    "is_message_event",
    "is_private_event",
]
