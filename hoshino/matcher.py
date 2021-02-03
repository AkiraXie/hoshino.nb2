'''
Author: AkiraXie
Date: 2021-01-28 14:34:06
LastEditors: AkiraXie
LastEditTime: 2021-02-02 19:58:30
Description: 
Github: http://github.com/AkiraXie/
'''
from typing import Any, Optional
from nonebot.adapters.cqhttp.message import MessageSegment,Message
from nonebot.adapters.cqhttp.event import Event,GroupMessageEvent
from nonebot.matcher import Matcher, matchers
from nonebot.plugin import on_command, on_message,  on_startswith, on_endswith, on_notice, on_keyword, on_metaevent, on_request, on_shell_command



def get_matchers() -> list:
    return matchers.items()

'''
能直接用`at_sender`
async def matcher_send(matcher: Matcher, event: Event, text:Any=None,at_sender:bool=False,finish:bool=False):
    sender_id=0
    if isinstance(event,GroupMessageEvent) and at_sender:
        sender_id = event.get_user_id()
    if sender_id:
        # yyy重载了加号运算符，好耶
        reply=MessageSegment.at(sender_id)+'  '+text
    else:
        reply=Message(text)
    if not finish:
        await matcher.send(reply)
    else:
        await matcher.finish(reply)
'''