'''
Author: AkiraXie
Date: 2021-01-28 21:03:08
LastEditors: AkiraXie
LastEditTime: 2021-01-29 02:04:50
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
lssv = on_command('lssv', aliases={'服务列表', '功能列表'}, permission=ADMIN)
enable = on_command('enable', aliases={'开启服务', '打开服务', '启用服务'})
disable = on_command('disable', aliases={'关闭服务', '停用服务', '禁用服务'})


@lssv.handle()
async def _(bot: Bot, event: Event, state: T_State):
    if isinstance(event, GroupMessageEvent):
        state['gids'] = [event.group_id]
    elif isinstance(event, PrivateMessageEvent):
        msgs = event.get_plaintext().split(' ')
        gids = []
        for msg in msgs:
            if msg == '-a' or msg == '--all':
                state['all'] = True
            elif msg.isdigit():
                gids.append(int(msg))
            elif msg!='':
                await lssv.finish(f'群ID {msg}非法,只能为纯数字')
        if len(gids) != 0:
            state['gids'] = gids.copy()


@lssv.got('gids', prompt='请输入群号，并用空格隔开。')
async def _(bot: Bot, event: Event, state: T_State):
    if isinstance(state['gids'], str):
        msgs = state['gids'].split(' ')
        gids = []
        for msg in msgs:
            if msg == '-a' or msg == '--all':
                state['all'] = True
            elif msg.isdigit():
                gids.append(int(msg))
            elif msg!='':
                await lssv.finish(f'群ID {msg}非法,只能为纯数字')
        if len(gids) != 0:
            state['gids'] = gids.copy()
        else:
            lssv.finish('非法输入')

    verbose_all = state.get('all', False)
    svs = Service.get_loaded_services().values()
    for gid in state['gids']:
        glist = list(g['group_id'] for g in await bot.get_group_list())
        if gid not in glist:
            await lssv.send(f'Bot未加入{gid},查看失败')
            continue
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


@enable.handle()
async def _(bot: Bot, event: Event, state: T_State):
    services = []
    if isinstance(event, GroupMessageEvent):
        state['gids'] = [event.group_id]
        msgs = event.get_plaintext().split(' ')
        for msg in msgs:
            if msg.isdigit():
                await enable.finish(f'服务名称 {msg}非法，不能为纯数字')
            elif msg!='':
                services.append(msg)
        if len(services) != 0:
            state['services'] = services.copy()

    elif isinstance(event, PrivateMessageEvent):
        msgs = event.get_plaintext().split(' ')
        gids = []
        for msg in msgs:
            if msg.isdigit():
                gids.append(int(msg))
            elif msg!='':
                services.append(msg)
        if len(gids) != 0:
            state['gids'] = gids.copy()
        if len(services) != 0:
            state['services'] = services.copy()



@enable.got('gids', '请输入要开启服务的群id，用空格间隔')
@enable.got('services', '请输入服务名称，用空格间隔')
async def _(bot: Bot, event: Event, state: T_State):
    if isinstance(state['services'], str):
        service_msgs = state['services'].split(' ')
        services = []
        for msg in service_msgs:
            if msg.isdigit():
                await enable.finish(f'服务名称 {msg}非法，不能为纯数字')
            elif msg!='':
                services.append(msg)
        if len(services) != 0:
            state['services'] = services.copy()
        else:
            enable.finish('非法输入')
    if isinstance(state['gids'], str):
        msgs = state['gids'].split(' ')
        gids = []
        for msg in msgs:
            if msg.isdigit():
                gids.append(int(msg))
            elif msg!='':
                await enable.finish(f'群ID {msg}非法,只能为纯数字')
        if len(gids) != 0:
            state['gids'] = gids.copy()
        else:
            enable.finish('非法输入')
    svs = Service.get_loaded_services()
    succ, notfound = set(), set()
    succ_group=set()
    for gid in state['gids']:
        glist = list(g['group_id'] for g in await bot.get_group_list())
        if gid not in glist:
            await enable.send(f'Bot未加入{gid},开启失败')
            continue
        for name in state['services']:
            if name in svs:
                sv = svs[name]
                if await sv.manage_perm(bot, event):
                    sv.set_enable(gid)
                    succ.add(name)
                    succ_group.add(str(gid))
            else:
                notfound.add(name)
    reply = []
    if succ:
        if isinstance(event, GroupMessageEvent):
            reply.append(f'已开启服务: {",".join(succ)}')
        else:
            reply.append(f'已在群{",".join(succ_group)}开启服务: {",".join(succ)}')
    if notfound:
        reply.append(f'未找到服务: {",".join(notfound)}')
    await enable.finish('\n'.join(reply))


@disable.handle()
async def _(bot: Bot, event: Event, state: T_State):
    services = []
    if isinstance(event, GroupMessageEvent):
        state['gids'] = [event.group_id]
        msgs = event.get_plaintext().split(' ')
        for msg in msgs:
            if msg.isdigit():
                await disable.finish(f'服务名称 {msg}非法，不能为纯数字')
            elif msg!='':
                services.append(msg)
        if len(services) != 0:
            state['services'] = services.copy()

    elif isinstance(event, PrivateMessageEvent):
        msgs = event.get_plaintext().split(' ')
        if len(msgs)==0:
            return
        gids = []
        for msg in msgs:
            if msg.isdigit():
                gids.append(int(msg))
            elif msg!='':
                services.append(msg)
        if len(gids) != 0:
            state['gids'] = gids.copy()
        if len(services) != 0:
            state['services'] = services.copy()



@disable.got('gids', '请输入要关闭服务的群id，用空格间隔')
@disable.got('services', '请输入服务名称，用空格间隔')
async def _(bot: Bot, event: Event, state: T_State):
    if isinstance(state['services'], str):
        service_msgs = state['services'].split(' ')
        services = []
        for msg in service_msgs:
            if msg.isdigit():
                await disable.finish(f'服务名称 {msg}非法，不能为纯数字')
            elif msg!='':
                services.append(msg)
        if len(services) != 0:
            state['services'] = services.copy()
        else:
            disable.finish('非法输入')
    if isinstance(state['gids'], str):
        msgs = state['gids'].split(' ')
        gids = []
        for msg in msgs:
            if msg.isdigit():
                gids.append(int(msg))
            elif msg!='':
                await disable.finish(f'群ID {msg}非法,只能为纯数字')
        if len(gids) != 0:
            state['gids'] = gids.copy()
        else:
            disable.finish('非法输入')
    svs = Service.get_loaded_services()
    succ, notfound = set(), set()
    succ_group=set()
    for gid in state['gids']:
        glist = list(g['group_id'] for g in await bot.get_group_list())
        if gid not in glist:
            await disable.send(f'Bot未加入{gid},关闭失败')
            continue
        for name in state['services']:
            if name in svs:
                sv = svs[name]
                if await sv.manage_perm(bot, event):
                    sv.set_disable(gid)
                    succ.add(name)
                    succ_group.add(str(gid))
            else:
                notfound.add(name)
    reply = []
    if succ:
        if isinstance(event, GroupMessageEvent):
            reply.append(f'已关闭服务: {",".join(succ)}')
        else:
            reply.append(f'已在群 {",".join(succ_group)}关闭服务: {",".join(succ)}')
    if notfound:
        reply.append(f'未找到服务: {",".join(notfound)}')
    await disable.finish('\n'.join(reply))
