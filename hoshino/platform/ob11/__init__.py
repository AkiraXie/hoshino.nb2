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
from .depends import (
    EventMessage as EventMessage,
    GroupID as GroupID,
    GroupMemberName as GroupMemberName,
    MessageID as MessageID,
    PlainText as PlainText,
    RawMessage as RawMessage,
    ReplyMessage as ReplyMessage,
    SenderID as SenderID,
)

__all__ = [
    "Adapter",
    "Bot",
    "EventMessage",
    "Event",
    "GroupID",
    "GroupMessageEvent",
    "GroupMemberName",
    "GroupMsgEmojiLikeEvent",
    "GroupReactionEvent",
    "Message",
    "MessageEvent",
    "MessageID",
    "MessageSegment",
    "NoticeEvent",
    "PlainText",
    "PrivateMessageEvent",
    "RawMessage",
    "ReplyMessage",
    "SenderID",
    "escape",
]
