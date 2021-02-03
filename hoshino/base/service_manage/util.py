'''
Author: AkiraXie
Date: 2021-01-29 12:56:12
LastEditors: AkiraXie
LastEditTime: 2021-02-03 23:05:25
Description: 
Github: http://github.com/AkiraXie/
'''
import re
from typing import Type
from hoshino.matcher import Matcher
from . import GroupMessageEvent, Service, Bot, Event, T_State, enable, disable


async def parse_service(bot: Bot, event: Event, state: T_State):
    service_msgs = event.get_plaintext().split(' ')
    services = []
    for msg in service_msgs:
        if msg != '':
            services.append(msg)
    if len(services) != 0:
        state['services'] = services.copy()


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


async def manage_service(matcher: Type[Matcher], bot: Bot, event: Event, state: T_State):
    assert matcher in (enable, disable), 'Matcher must be enable or disable'
    svs = Service.get_loaded_services()
    if  'all' in state['args'].__dict__ and state['args'].all:
        state['services'] = svs.keys()
    allsv = set(svs.keys())
    exclude = set()
    succ, notfound = set(), set()
    succ_group = set()
    for name in state['services']:
        flag = 1
        if name.startswith(('!', '！')) or name.endswith(('!', '！')):
            name = re.sub(r'[!！]', '', name)
            flag = 0
        if name in svs:
            sv = svs[name]
            if await sv.manage_perm(bot, event):
                if flag:
                    succ.add(name)
                else:
                    exclude.add(name)
        else:
            notfound.add(name)
    if not succ:
        await matcher.finish(f'未找到服务: {",".join(notfound)}') if notfound else matcher.finish()
    succ = succ if not exclude else allsv-exclude
    for gid in state['gids']:
        for name in succ:
            sv=svs[name]
            sv.set_enable(gid) if matcher == enable else sv.set_disable(gid)
        succ_group.add(str(gid))
    reply = []
    if matcher == enable:
        if isinstance(event, GroupMessageEvent):
            reply.append(f'已开启服务: {",".join(succ)}')
        else:
            reply.append(f'已在群 {",".join(succ_group)}开启服务: {",".join(succ)}')
    if matcher == disable:
        if isinstance(event, GroupMessageEvent):
            reply.append(f'已关闭服务: {",".join(succ)}')
        else:
            reply.append(f'已在群 {",".join(succ_group)}关闭服务: {",".join(succ)}')
    if notfound:
        reply.append(f'未找到服务: {",".join(notfound)}')
    await matcher.finish('\n'.join(reply))
