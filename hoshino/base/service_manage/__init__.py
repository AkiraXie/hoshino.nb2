"""
Author: AkiraXie
Date: 2021-01-29 12:54:47
LastEditors: AkiraXie
LastEditTime: 2022-02-17 00:52:33
Description:
Github: http://github.com/AkiraXie/
"""

import re
from functools import cmp_to_key
from hoshino.event import GroupMessageEvent, PrivateMessageEvent
from hoshino import Service, Bot, Event
from hoshino.rule import to_me, ArgumentParser
from hoshino.permission import ADMIN
from hoshino.matcher import on_shell_command
from hoshino.util import text_to_segment, _strip_cmd
from hoshino.typing import T_State, FinishedException
from .util import parse_gid, parse_service

parser = ArgumentParser()
parser.add_argument("-a", "--all", action="store_true")
parser.add_argument("-p", "--picture", action="store_true")
parser.add_argument("-i", "--invisible", action="store_true")
parser1 = ArgumentParser()
parser1.add_argument("-a", "--all", action="store_true")
lssv = on_shell_command(
    "lssv",
    to_me(),
    aliases={"服务列表", "功能列表"},
    permission=ADMIN,
    parser=parser,
    block=True,
    handlers=[_strip_cmd],
)
enable = on_shell_command(
    "enable",
    to_me(),
    aliases={"开启", "打开", "启用"},
    parser=parser1,
    state={"action": "开启"},
    block=True,
    handlers=[_strip_cmd],
)
disable = on_shell_command(
    "disable",
    to_me(),
    aliases={"关闭", "停用", "禁用"},
    parser=parser1,
    state={"action": "关闭"},
    block=True,
    handlers=[_strip_cmd],
)


@lssv.handle()
async def _(event: Event, state: T_State):
    if isinstance(event, GroupMessageEvent):
        state["gids"] = [event.group_id]


@lssv.got("gids", prompt="请输入群号，并用空格隔开。", args_parser=parse_gid)
async def _(bot: Bot, event: Event, state: T_State):
    if not "gids" in state:
        await bot.send(event, "无效输入")
        raise FinishedException
    verbose_all = state["_args"].all
    as_pic = state["_args"].picture
    verbose_hide = state["_args"].invisible
    svs = Service.get_loaded_services().values()
    for gid in state["gids"]:
        current_svs = map(lambda sv: (sv, sv.check_enabled(gid)), svs)
        cmpfunc = cmp_to_key(
            lambda x, y: (y[1] - x[1])
            or (-1 if x[0].name < y[0].name else 1 if x[0].name > y[0].name else 0)
        )
        current_svs = sorted(current_svs, key=cmpfunc)
        reply = [f"群{gid}服务一览："]
        for sv, on in current_svs:
            if verbose_all:
                ox = "O" if on else "X"
                reply.append(f"|{ox}| {sv.name}")
            elif verbose_hide:
                if not sv.visible:
                    ox = "O" if on else "X"
                    reply.append(f"|{ox}| {sv.name}")
            elif sv.visible:
                ox = "O" if on else "X"
                reply.append(f"|{ox}| {sv.name}")
        await lssv.finish("\n".join(reply)) if not as_pic else await lssv.finish(
            text_to_segment("\n".join(reply))
        )


async def handle_msg(bot: Bot, event: Event, state: T_State):
    if isinstance(event, GroupMessageEvent):
        state["gids"] = [event.group_id]
        await parse_service(event, state)

    elif isinstance(event, PrivateMessageEvent):
        services = []
        glist = list(g["group_id"] for g in await bot.get_group_list())
        failure = set()
        msgs = event.get_plaintext().split(" ")
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
                services.append(msg)
        if failure:
            await enable.send(f'bot未入群 {", ".join(failure)}')
        if len(gids) != 0:
            state["gids"] = gids.copy()
        if len(services) != 0:
            state["services"] = services.copy()


disable.handle()(handle_msg)
enable.handle()(handle_msg)


@disable.got("gids", "请输入要关闭服务的群ID，用空格间隔", args_parser=parse_gid)
@disable.got("services", "请输入服务名称，用空格间隔", args_parser=parse_service)
@enable.got("gids", "请输入要开启服务的群ID，用空格间隔", args_parser=parse_gid)
@enable.got("services", "请输入服务名称，用空格间隔", args_parser=parse_service)
async def _(bot: Bot, event: Event, state: T_State):
    if not state["gids"] or not state["services"]:
        await bot.send(event, "无效输入")
        raise FinishedException
    action = state["action"]
    svs = Service.get_loaded_services()
    if "all" in state["_args"].__dict__ and state["_args"].all:
        state["services"] = svs.keys()
    allsv = set(svs.keys())
    exclude, succ, notfound, succ_group = set(), set(), set(), set()
    for name in state["services"]:
        flag = 1
        if name.startswith(("!", "！")) or name.endswith(("!", "！")):
            name = re.sub(r"[!！]", "", name)
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
    if not succ and notfound:
        await bot.send(event, f'未找到服务: {", ".join(notfound)}')
        raise FinishedException
    succ = succ if not exclude else allsv - exclude
    for gid in state["gids"]:
        for name in succ:
            sv = svs[name]
            sv.set_enable(gid) if action == "开启" else sv.set_disable(gid)
        succ_group.add(str(gid))
    reply = []
    if isinstance(event, GroupMessageEvent):
        reply.append(f'已{action}服务: {", ".join(succ)}')
    else:
        reply.append(f'已在群 {", ".join(succ_group)}{action}服务: {", ".join(succ)}')
    if notfound:
        reply.append(f'未找到服务: {", ".join(notfound)}')
    await bot.send(event, "\n".join(reply))
    raise FinishedException
