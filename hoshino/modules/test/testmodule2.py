'''
Author: AkiraXie
Date: 2021-01-29 01:13:36
LastEditors: AkiraXie
LastEditTime: 2021-01-29 01:27:48
Description: 
Github: http://github.com/AkiraXie/
'''
from hoshino.typing import T_State
from hoshino import Service, Bot,Event
sv=Service('testrex')
rex=sv.on_regex(r'^高情商(.+)低情商(.+)',only_group=0)
@rex.handle()
async def _(bot:Bot,event:Event,state:T_State):
    match=state['match']
    await rex.send(f"高情商:{match.group(1)}\n低情商:{match.group(2)}")