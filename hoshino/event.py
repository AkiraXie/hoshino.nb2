'''
Author: AkiraXie
Date: 2022-02-26 00:16:33
LastEditors: AkiraXie
LastEditTime: 2022-03-08 02:16:47
Description: 
Github: http://github.com/AkiraXie/
'''
from nonebot.adapters.onebot.v11 import Event
from nonebot.adapters.onebot.v11.event import (
    MessageEvent,
    GroupMessageEvent,
    PrivateMessageEvent,
    LifecycleMetaEvent,
)


def get_event(event: Event) -> str:
    return str(event.__dict__)
