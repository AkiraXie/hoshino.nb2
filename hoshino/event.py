'''
Author: AkiraXie
Date: 2021-01-28 14:58:20
LastEditors: AkiraXie
LastEditTime: 2021-03-03 02:17:34
Description: 
Github: http://github.com/AkiraXie/
'''
from nonebot.adapters.cqhttp import Event
from nonebot.adapters.cqhttp.event import GroupMessageEvent, PrivateMessageEvent, LifecycleMetaEvent


def get_event(event: Event) -> str:
    return str(event.__dict__)
