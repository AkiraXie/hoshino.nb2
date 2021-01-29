'''
Author: AkiraXie
Date: 2021-01-29 01:13:36
LastEditors: AkiraXie
LastEditTime: 2021-01-29 14:58:43
Description: 
Github: http://github.com/AkiraXie/
'''
from hoshino.typing import T_State
from hoshino import Service, Bot, Event
sv = Service('testrex')
rex = sv.on_regex(r'^高情商(.+)低情商(.+)', only_group=0, only_to_me=1)


@rex.handle()
async def _(bot: Bot, event: Event, state: T_State):
    match = state['match']
    await rex.send(f"高情商:{match.group(1)}\n低情商:{match.group(2)}")
start = sv.on_startswith('rank', only_group=0, only_to_me=1)


@start.handle()
async def _(bot: Bot, event: Event, state: T_State):
    await start.send(event.get_plaintext())
end = sv.on_endswith('谁', only_group=0, only_to_me=1)


@end.handle()
async def _(bot: Bot, event: Event, state: T_State):
    await start.send(event.get_plaintext())
