"""OneBot v11 containment — 全部 OneBot 符号的唯一入口"""

from .events import (
    GroupMsgEmojiLikeEvent as GroupMsgEmojiLikeEvent,
)
from .events import (
    GroupReactionEvent as GroupReactionEvent,
)
from .types import (
    Adapter as Adapter,
)
from .types import (
    Bot as Bot,
)
from .types import (
    Event as Event,
)
from .types import (
    GroupMessageEvent as GroupMessageEvent,
)
from .types import (
    Message as Message,
)
from .types import (
    MessageEvent as MessageEvent,
)
from .types import (
    MessageSegment as MessageSegment,
)
from .types import (
    NoticeEvent as NoticeEvent,
)
from .types import (
    PrivateMessageEvent as PrivateMessageEvent,
)
from .types import (
    escape as escape,
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
