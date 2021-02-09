'''
Author: AkiraXie
Date: 2021-02-06 21:22:43
LastEditors: AkiraXie
LastEditTime: 2021-02-06 21:36:44
Description: 
Github: http://github.com/AkiraXie/
'''
from hoshino import Service,Bot,Event,Message
from nonebot.adapters.cqhttp.event import PokeNotifyEvent
from hoshino.typing import T_State
sv=Service('poke')
poke=sv.on_notice(False)
@poke.handle()
async def _(bot:Bot,event:Event):
    if isinstance(event,PokeNotifyEvent):
        if event.is_tome() and event.user_id!=event.self_id:
            await poke.finish(Message(f'[CQ:poke,qq={event.user_id}]'))
    else:
        await poke.finish()