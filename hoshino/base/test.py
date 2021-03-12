'''
Author: AkiraXie
Date: 2021-01-28 02:32:32
LastEditors: AkiraXie
LastEditTime: 2021-03-12 17:19:04
Description: 
Github: http://github.com/AkiraXie/
'''
from nonebot.adapters.cqhttp.event import GroupMessageEvent
from nonebot.permission import Permission
from nonebot.typing import T_State
from hoshino.matcher import get_matchers, Matcher
from hoshino.event import Event, get_event
from hoshino import Bot, get_bot_list,sucmd
test1 = sucmd('testgetbot', True)
test2 = sucmd('testmatchers', True)
test3 = sucmd('testevent', True)


@test1.handle()
async def _(bot: Bot):
    await test1.finish(str(get_bot_list()))


@test2.handle()
async def _(bot: Bot):
    await test2.finish(str(get_matchers()))


@test3.handle()
async def _(bot: Bot, event: Event):
    await test3.finish(get_event(event))
    
    
mt = sucmd('testpu')


@mt.permission_updater
async def _(matcher: Matcher, bot: Bot, event: Event, state: T_State, permission: Permission) -> Permission:
    uid = event.get_user_id()
    gid = event.group_id

    async def _permission(bot: Bot, event: Event):
        return isinstance(event, GroupMessageEvent) and event.group_id == gid and event.get_user_id() == uid and await permission(bot, event)
    return Permission(_permission)


@mt.handle()
async def _(bot: Bot):
    await mt.send('第一次handle')


@mt.got('key', '请输入key')
async def _(bot: Bot, event: Event, state: T_State):
    await mt.send('测试成功！{key}'.format(**state))
