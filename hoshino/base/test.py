'''
Author: AkiraXie
Date: 2021-01-28 02:32:32
LastEditors: AkiraXie
LastEditTime: 2021-02-01 03:17:25
Description: 
Github: http://github.com/AkiraXie/
'''
from hoshino.rule import to_me
from hoshino.matcher import get_matchers
from hoshino.event import Event, get_event
from hoshino import Bot, get_bot_list, sucmd
test1 = sucmd('testgetbot', to_me())
test2 = sucmd('testmatchers', to_me())
test3 = sucmd('testevent', to_me())


@test1.handle()
async def _(bot: Bot):
    await test1.finish(str(get_bot_list()))


@test2.handle()
async def _(bot: Bot):
    await test2.finish(str(get_matchers()))


@test3.handle()
async def _(bot: Bot, event: Event):
    await test3.finish(get_event(event))
