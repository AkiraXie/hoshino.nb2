'''
Author: AkiraXie
Date: 2021-01-29 12:54:47
LastEditors: AkiraXie
LastEditTime: 2021-02-12 20:21:21
Description:
Github: http://github.com/AkiraXie/
'''
from functools import cmp_to_key

from nonebot.exception import FinishedException
from nonebot.rule import ArgumentParser
from hoshino.event import GroupMessageEvent, PrivateMessageEvent
from hoshino import Service, Bot, Event
from hoshino.rule import to_me
from hoshino.permission import ADMIN
from hoshino.matcher import  on_shell_command
from hoshino.util import text2Seg
from hoshino.typing import T_State
parser = ArgumentParser()
parser.add_argument('-a', '--all', action='store_true')
parser.add_argument('-p', '--picture', action='store_true')
parser1 = ArgumentParser()
parser1.add_argument('-a', '--all', action='store_true')
lssv = on_shell_command('lssv', to_me(), aliases={
                        '服务列表', '功能列表'}, permission=ADMIN, parser=parser)
enable =on_shell_command('enable', to_me(), aliases={'开启', '打开', '启用'},parser=parser1)
disable =on_shell_command('disable', to_me(), aliases={'关闭', '停用', '禁用'},parser=parser1)
from .util import manage_service, parse_gid, parse_service

@lssv.handle()
async def _(bot: Bot, event: Event, state: T_State):
    if isinstance(event, GroupMessageEvent):
        state['gids'] = [event.group_id]


@lssv.got('gids', prompt='请输入群号，并用空格隔开。', args_parser=parse_gid)
async def _(bot: Bot, event: Event, state: T_State):
    if not 'gids' in state:
        await bot.send(event, '无效输入')
        raise FinishedException
    verbose_all = state['args'].all
    as_pic = state['args'].picture
    svs = Service.get_loaded_services().values()
    for gid in state['gids']:
        current_svs = map(lambda sv: (sv, sv.check_enabled(gid)), svs)
        cmpfunc = cmp_to_key(lambda x, y: (
            y[1] - x[1]) or (-1 if x[0].name < y[0].name else 1 if x[0].name > y[0].name else 0))
        current_svs = sorted(current_svs, key=cmpfunc)
        reply = [f'群{gid}服务一览：']
        for sv, on in current_svs:
            if sv.visible or verbose_all:
                ox = 'O' if on else 'X'
                reply.append(f"|{ox}| {sv.name}")
        await lssv.finish("\n".join(reply)) if not as_pic else await lssv.finish(text2Seg("\n".join(reply)))


@disable.handle()
async def _(bot: Bot, event: Event, state: T_State):
    services = []
    if isinstance(event, GroupMessageEvent):
        state['gids'] = [event.group_id]
        await parse_service(bot, event, state)

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
            elif msg != '':
                services.append(msg)
        if failure:
            await disable.send(f'bot未入群 {"，".join(failure)}')
        if len(gids) != 0:
            state['gids'] = gids.copy()
        if len(services) != 0:
            state['services'] = services.copy()


@disable.got('gids', '请输入要关闭服务的群ID，用空格间隔', args_parser=parse_gid)
@disable.got('services', '请输入服务名称，用空格间隔', args_parser=parse_service)
async def _(bot: Bot, event: Event, state: T_State):
    if not state['gids'] or not state['services']:
        await bot.send(event, '无效输入')
        raise FinishedException
    await manage_service(disable, bot, event, state)


@enable.handle()
async def _(bot: Bot, event: Event, state: T_State):
    services = []
    if isinstance(event, GroupMessageEvent):
        state['gids'] = [event.group_id]
        await parse_service(bot, event, state)

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
            elif msg != '':
                services.append(msg)
        if failure:
            await enable.send(f'bot未入群 {"，".join(failure)}')
        if len(gids) != 0:
            state['gids'] = gids.copy()
        if len(services) != 0:
            state['services'] = services.copy()


@enable.got('gids', '请输入要开启服务的群ID，用空格间隔', args_parser=parse_gid)
@enable.got('services', '请输入服务名称，用空格间隔', args_parser=parse_service)
async def _(bot: Bot, event: Event, state: T_State):
    if not state['gids'] or not state['services']:
        await bot.send(event, '无效输入')
        raise FinishedException
    await manage_service(enable, bot, event, state)
