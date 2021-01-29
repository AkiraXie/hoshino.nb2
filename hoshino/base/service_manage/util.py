'''
Author: AkiraXie
Date: 2021-01-29 12:56:12
LastEditors: AkiraXie
LastEditTime: 2021-01-29 23:59:52
Description: 
Github: http://github.com/AkiraXie/
'''
from nonebot.exception import FinishedException
from hoshino.matcher import Matcher
from . import GroupMessageEvent, Service, Bot, Event, T_State


async def parse_service(bot: Bot, event: Event, state: T_State):
    service_msgs = event.get_plaintext().split(' ')
    services = []
    for msg in service_msgs:
        if msg != '':
            services.append(msg)
    if len(services) != 0:
        state['services'] = services.copy()
    else:
        await bot.send(event, '无效输入')
        raise FinishedException


async def parse_gid(bot: Bot, event: Event, state: T_State):
    msgs = event.get_plaintext().split(' ')
    glist = list(g['group_id'] for g in await bot.get_group_list())
    failure = set()
    illegal = set()
    gids = []
    for msg in msgs:
        if msg.isdigit():
            gid = int(msg)
            if gid not in glist:
                failure.add(msg)
                continue
            else:
                gids.append(gid)
        elif msg != '':
            illegal.add(msg)
    if illegal:
        await bot.send(event, f'"{"，".join(illegal)}"无效，群ID只能为纯数字')
    if failure:
        await bot.send(event, f'bot未入群 {"，".join(failure)}')
    if len(gids) != 0:
        state['gids'] = gids.copy()
    else:
        await bot.send(event, '无效输入')
        raise FinishedException


async def lssv_parse_gid(bot: Bot, event: Event, state: T_State):
    msgs = event.get_plaintext().split(' ')
    glist = list(g['group_id'] for g in await bot.get_group_list())
    failure = set()
    illegal = set()
    gids = []
    for msg in msgs:
        if msg.isdigit():
            gid = int(msg)
            if gid not in glist:
                failure.add(msg)
                continue
            else:
                gids.append(gid)
        elif msg == '-a' or msg == '--all':
            state['all'] = True
        elif msg != '':
            illegal.add(msg)
    if illegal:
        await bot.send(event, f'"{"，".join(illegal)}"无效，群ID只能为纯数字')
    if failure:
        await bot.send(event, f'bot未入群 {"，".join(failure)}')
    if len(gids) != 0:
        state['gids'] = gids.copy()
    else:
        await bot.send(event, '无效输入')
        raise FinishedException


async def manage_service(matcher: Matcher, bot: Bot, event: Event, state: T_State):
    from . import enable, disable
    assert matcher in (enable, disable), 'Matcher must be enable or disable'
    svs = Service.get_loaded_services()
    succ, notfound = set(), set()
    succ_group = set()
    for gid in state['gids']:
        for name in state['services']:
            if name in svs:
                sv = svs[name]
                if await sv.manage_perm(bot, event):
                    sv.set_enable(
                        gid) if matcher == enable else sv.set_disable(gid)
                    succ.add(name)
                    succ_group.add(str(gid))
            else:
                notfound.add(name)
    reply = []
    if succ and matcher == enable:
        if isinstance(event, GroupMessageEvent):
            reply.append(f'已开启服务: {",".join(succ)}')
        else:
            reply.append(f'已在群 {",".join(succ_group)}开启服务: {",".join(succ)}')
    if succ and matcher == disable:
        if isinstance(event, GroupMessageEvent):
            reply.append(f'已关闭服务: {",".join(succ)}')
        else:
            reply.append(f'已在群 {",".join(succ_group)}关闭服务: {",".join(succ)}')
    if notfound:
        reply.append(f'未找到服务: {",".join(notfound)}')
    await matcher.finish('\n'.join(reply))
