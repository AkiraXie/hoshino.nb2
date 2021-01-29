'''
Author: AkiraXie
Date: 2021-01-29 12:54:47
LastEditors: AkiraXie
LastEditTime: 2021-01-29 14:55:02
Description: 
Github: http://github.com/AkiraXie/
'''
from functools import cmp_to_key
from hoshino.event import GroupMessageEvent, PrivateMessageEvent
from hoshino import Service, Bot, Event, service
from hoshino import permission
from hoshino.permission import ADMIN
from hoshino.matcher import on_command
from hoshino.typing import T_State
from .util import manage_service, parse_gid, lssv_parse_gid, parse_service
lssv = on_command('lssv', aliases={'服务列表', '功能列表'}, permission=ADMIN)
enable = on_command('enable', aliases={'开启服务', '打开服务', '启用服务'})
disable = on_command('disable', aliases={'关闭服务', '停用服务', '禁用服务'})


@lssv.handle()
async def _(bot: Bot, event: Event, state: T_State):
    if isinstance(event, GroupMessageEvent):
        state['gids'] = [event.group_id]
    elif isinstance(event, PrivateMessageEvent):
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
            await lssv.send(f'"{"，".join(illegal)}"无效，群ID只能为纯数字')
        if failure:
            await lssv.send(f'bot未入群 {"，".join(failure)}')
        if len(gids) != 0:
            state['gids'] = gids.copy()


@lssv.got('gids', prompt='请输入群号，并用空格隔开。', args_parser=lssv_parse_gid)
async def _(bot: Bot, event: Event, state: T_State):
    verbose_all = state.get('all', False)
    svs = Service.get_loaded_services().values()
    for gid in state['gids']:
        current_svs = map(lambda sv: (sv, sv.check_enabled(gid)), svs)
        cmpfunc = cmp_to_key(lambda x, y: (
            y[1] - x[1]) or (-1 if x[0].name < y[0].name else 1 if x[0].name > y[0].name else 0))
        current_svs = sorted(current_svs, key=cmpfunc)
        reply = [f'群{gid}服务一览：']
        for sv, on in current_svs:
            if sv.visible or verbose_all:
                ox = '○' if on else '×'
                reply.append(f"|{ox}| {sv.name}")
        await lssv.send("\n".join(reply))


@disable.handle()
async def _(bot: Bot, event: Event, state: T_State):
    services = []
    if isinstance(event, GroupMessageEvent):
        state['gids'] = [event.group_id]
        msgs = event.get_plaintext().split(' ')
        for msg in msgs:
            if msg!='':
                services.append(msg)
        if len(services) != 0:
            state['services'] = services.copy()

    elif isinstance(event, PrivateMessageEvent):
        glist = list(g['group_id'] for g in await bot.get_group_list())
        failure = set()
        msgs = event.get_plaintext().split(' ')
        gids = []
        for msg in msgs:
            if msg.isdigit():
                gid = int(msg)
                if gid not in glist:
                    failure.add(msg)
                    continue
                else:
                    gids.append(gid)
            elif msg!='':
                services.append(msg)
        if failure:
            await disable.send(f'bot未入群 {"，".join(failure)}')
        if len(gids) != 0:
            state['gids'] = gids.copy()
        if len(services) != 0:
            state['services'] = services.copy()


@disable.got('gids', '请输入要关闭服务的群ID，用空格间隔',args_parser=parse_gid)
@disable.got('services', '请输入服务名称，用空格间隔',args_parser=parse_service)
async def _(bot: Bot, event: Event, state: T_State):
    await manage_service(disable,bot,event,state)



@enable.handle()
async def _(bot: Bot, event: Event, state: T_State):
    services = []
    if isinstance(event, GroupMessageEvent):
        state['gids'] = [event.group_id]
        msgs = event.get_plaintext().split(' ')
        for msg in msgs:
            if msg!='':
                services.append(msg)
        if len(services) != 0:
            state['services'] = services.copy()

    elif isinstance(event, PrivateMessageEvent):
        glist = list(g['group_id'] for g in await bot.get_group_list())
        failure = set()
        msgs = event.get_plaintext().split(' ')
        gids = []
        for msg in msgs:
            if msg.isdigit():
                gid = int(msg)
                if gid not in glist:
                    failure.add(msg)
                    continue
                else:
                    gids.append(gid)
            elif msg!='':
                services.append(msg)
        if failure:
            await enable.send(f'bot未入群 {"，".join(failure)}')
        if len(gids) != 0:
            state['gids'] = gids.copy()
        if len(services) != 0:
            state['services'] = services.copy()



@enable.got('gids', '请输入要开启服务的群ID，用空格间隔',args_parser=parse_gid)
@enable.got('services', '请输入服务名称，用空格间隔',args_parser=parse_service)
async def _(bot: Bot, event: Event, state: T_State):
    await manage_service(enable,bot,event,state)