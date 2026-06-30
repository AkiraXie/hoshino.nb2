"""OneBot v11 containment — 全部 OneBot 符号的唯一入口"""

from .types import (
    Adapter as Adapter,
    Bot as Bot,
    Event as Event,
    GroupMessageEvent as GroupMessageEvent,
    MessageEvent as MessageEvent,
    Message as Message,
    MessageSegment as MessageSegment,
    NoticeEvent as NoticeEvent,
    PrivateMessageEvent as PrivateMessageEvent,
    escape as escape,
)
from .events import (
    GroupMsgEmojiLikeEvent as GroupMsgEmojiLikeEvent,
    GroupReactionEvent as GroupReactionEvent,
)

__all__ = [
    "Adapter",
    "Bot",
    "Event",
    "GroupMessageEvent",
    "GroupMsgEmojiLikeEvent",
    "GroupReactionEvent",
    "Message",
    "MessageEvent",
    "MessageSegment",
    "NoticeEvent",
    "PrivateMessageEvent",
    "escape",
]
