from nonebot.adapters.onebot.v11 import Event
from nonebot.adapters.onebot.v11.event import (
    MessageEvent,
    GroupMessageEvent,
    PrivateMessageEvent,
    LifecycleMetaEvent,
)


def get_event(event: Event) -> str:
    return str(event.__dict__)
