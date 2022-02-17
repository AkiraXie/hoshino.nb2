"""
Author: AkiraXie
Date: 2021-01-28 14:58:20
LastEditors: AkiraXie
LastEditTime: 2022-02-16 17:19:30
Description: 
Github: http://github.com/AkiraXie/
"""
from nonebot.adapters.onebot.v11 import Event
from nonebot.adapters.onebot.v11.event import (
    GroupMessageEvent,
    PrivateMessageEvent,
    LifecycleMetaEvent,
)


def get_event(event: Event) -> str:
    return str(event.__dict__)
