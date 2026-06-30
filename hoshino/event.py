"""Event types — compat re-export from platform/ob11 + platform helpers"""

from hoshino.platform.event import (
    is_group_event as is_group_event,
    is_private_event as is_private_event,
)
from hoshino.platform.ob11 import (
    Event as Event,
    GroupMessageEvent as GroupMessageEvent,
    GroupMsgEmojiLikeEvent as GroupMsgEmojiLikeEvent,
    GroupReactionEvent as GroupReactionEvent,
    MessageEvent as MessageEvent,
    NoticeEvent as NoticeEvent,
    PrivateMessageEvent as PrivateMessageEvent,
)


def get_event(event: Event) -> str:
    return str(event.__dict__)
