"""
Author: AkiraXie
Date: 2021-01-29 12:56:12
LastEditors: AkiraXie
LastEditTime: 2022-02-17 00:28:11
Description: 
Github: http://github.com/AkiraXie/
"""
from . import Bot, Event, T_State


async def parse_service(event: Event, state: T_State):
    service_msgs = event.get_plaintext().split()
    services = []
    for msg in service_msgs:
        if msg != "":
            services.append(msg)
    if len(services) != 0:
        state["services"] = services.copy()


async def parse_gid(bot: Bot, event: Event, state: T_State):
    msgs = event.get_plaintext().split()
    glist = list(g["group_id"] for g in await bot.get_group_list())
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
        elif msg != "":
            illegal.add(msg)
    if illegal:
        await bot.send(event, f'"{"，".join(illegal)}"无效，群ID只能为纯数字')
    if failure:
        await bot.send(event, f'bot未入群 {"，".join(failure)}')
    if len(gids) != 0:
        state["gids"] = gids.copy()
