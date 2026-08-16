"""Telegram adapter types and helpers."""

from hoshino.platform.telegram.event import (
    get_chat_id as get_chat_id,
)
from hoshino.platform.telegram.event import (
    get_event_message as get_event_message,
)
from hoshino.platform.telegram.event import (
    get_group_id as get_group_id,
)
from hoshino.platform.telegram.event import (
    get_message_id as get_message_id,
)
from hoshino.platform.telegram.event import (
    get_plaintext as get_plaintext,
)
from hoshino.platform.telegram.event import (
    get_reply_message as get_reply_message,
)
from hoshino.platform.telegram.event import (
    get_session_id as get_session_id,
)
from hoshino.platform.telegram.event import (
    get_user_id as get_user_id,
)
from hoshino.platform.telegram.event import (
    is_group_event as is_group_event,
)
from hoshino.platform.telegram.event import (
    is_message_event as is_message_event,
)
from hoshino.platform.telegram.event import (
    is_private_event as is_private_event,
)
from hoshino.platform.telegram.types import (
    Adapter as Adapter,
)
from hoshino.platform.telegram.types import (
    Bot as Bot,
)
from hoshino.platform.telegram.types import (
    Event as Event,
)
from hoshino.platform.telegram.types import (
    Message as Message,
)
from hoshino.platform.telegram.types import (
    MessageReactionEvent as MessageReactionEvent,
)
from hoshino.platform.telegram.types import (
    MessageSegment as MessageSegment,
)

__all__ = [
    "Adapter",
    "Bot",
    "Event",
    "Message",
    "MessageReactionEvent",
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
