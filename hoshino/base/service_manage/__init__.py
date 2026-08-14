import re
from functools import cmp_to_key

from nonebot.adapters import Bot, Event
from nonebot.rule import to_me

from hoshino.command import (
    Alconna,
    AlconnaMatches,
    Args,
    At,
    MultiVar,
    Option,
    UniMessage,
    UniMsg,
    on_alconna,
    CommandMeta
)
from hoshino.platform.permission import ADMIN
from hoshino.platform import (
    event_scope_key,
    get_group_id,
    get_group_list,
    group_scope_key,
    is_group_event,
    platform_key,
)
from hoshino.service import Service

compact_meta = CommandMeta(compact=True)

lssv = on_alconna(
    Alconna(
        "lssv",
        Args["gids", MultiVar(str, "*")],
        Option("--all|-a"),
        Option("--picture|-p"),
        Option("--invisible|-i"),
    ),
    rule=to_me(),
    aliases={"服务列表", "功能列表"},
    permission=ADMIN,
    block=True,
)
enable = on_alconna(
    Alconna("enable", Args["items", MultiVar(str, "*")], Option("--all|-a"),meta=compact_meta),
    rule=to_me(),
    aliases={"开启", "打开", "启用"},
    permission=ADMIN,
    block=True,
)
disable = on_alconna(
    Alconna("disable", Args["items", MultiVar(str, "*")], Option("--all|-a"),meta=compact_meta),
    rule=to_me(),
    aliases={"关闭", "停用", "禁用"},
    permission=ADMIN,
    block=True,
)


@lssv.handle()
async def _(bot: Bot, event: Event, gids: tuple[str, ...], matches=AlconnaMatches()):
    target_gids, failure, illegal = await _resolve_gids(bot, event, gids)
    if illegal:
        await lssv.send(f'"{"，".join(sorted(illegal))}"无效，群ID只能为纯数字')
    if failure:
        await lssv.send(f"bot未入群 {', '.join(sorted(failure))}")
    if not target_gids:
        await lssv.finish("无效输入")
    verbose_all = "all" in matches.options
    verbose_hide = "invisible" in matches.options
    svs = Service.get_loaded_services().values()
    for gid in target_gids:
        scope_key = (
            event_scope_key(bot, event)
            if is_group_event(event) and gid == get_group_id(event)
            else group_scope_key(gid, platform=platform_key(bot))
        )
        current_svs = map(lambda sv: (sv, sv.check_enabled(scope_key)), svs)
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
        await lssv.finish("\n".join(reply))


@enable.handle()
async def _(
    bot: Bot,
    event: Event,
    items: tuple[str, ...],
    msg: UniMsg,
    matches=AlconnaMatches(),
):
    reply = await _switch_services(
        bot,
        event,
        items,
        msg,
        action="开启",
        all_services="all" in matches.options,
    )
    await UniMessage.text(reply).finish()


@disable.handle()
async def _(
    bot: Bot,
    event: Event,
    items: tuple[str, ...],
    msg: UniMsg,
    matches=AlconnaMatches(),
):
    reply = await _switch_services(
        bot,
        event,
        items,
        msg,
        action="关闭",
        all_services="all" in matches.options,
    )
    await UniMessage.text(reply).finish()


async def _switch_services(
    bot: Bot,
    event: Event,
    items: tuple[str, ...],
    msg,
    *,
    action: str,
    all_services: bool,
) -> str:
    gids, services, failure = await _resolve_switch_targets(bot, event, items, msg)
    if failure:
        await UniMessage.text(f"bot未入群 {', '.join(sorted(failure))}").send()
    if not gids or (not services and not all_services):
        return "无效输入"
    svs = Service.get_loaded_services()
    if all_services:
        services = tuple(svs.keys())
    allsv = set(svs.keys())
    exclude, succ, notfound, succ_group = set(), set(), set(), set()
    for name in services:
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
        return f"未找到服务: {', '.join(notfound)}"
    succ = succ if not exclude else allsv - exclude
    for gid in gids:
        scope_key = (
            event_scope_key(bot, event)
            if is_group_event(event) and gid == get_group_id(event)
            else group_scope_key(gid, platform=platform_key(bot))
        )
        for name in succ:
            sv = svs[name]
            if action == "开启":
                sv.set_enable(scope_key)
            else:
                sv.set_disable(scope_key)
        succ_group.add(str(gid))
    reply = []
    if is_group_event(event):
        reply.append(f"已{action}服务: {', '.join(succ)}")
    else:
        reply.append(f"已在群 {', '.join(succ_group)} {action}服务: {', '.join(succ)}")
    if notfound:
        reply.append(f"未找到服务: {', '.join(notfound)}")
    return "\n".join(reply)


async def _resolve_switch_targets(
    bot: Bot,
    event: Event,
    items: tuple[str, ...],
    msg,
) -> tuple[list[int], tuple[str, ...], set[str]]:
    if (group_id := get_group_id(event)) is not None:
        return [group_id], tuple(item for item in items if item), set()

    group_ids = await _joined_group_ids(bot)
    gids: list[int] = []
    services: list[str] = []
    failure: set[str] = set()
    for item in items:
        if item.isdigit():
            gid = int(item)
            if gid in group_ids:
                gids.append(gid)
            else:
                failure.add(item)
        elif item:
            services.append(item)
    for at in msg.get(At):
        if at.target.isdigit():
            gid = int(at.target)
            if gid in group_ids:
                gids.append(gid)
            else:
                failure.add(at.target)
    return _dedupe_ints(gids), tuple(services), failure


async def _resolve_gids(
    bot: Bot,
    event: Event,
    values: tuple[str, ...],
) -> tuple[list[int], set[str], set[str]]:
    if (group_id := get_group_id(event)) is not None and not values:
        return [group_id], set(), set()
    group_ids = await _joined_group_ids(bot)
    gids: list[int] = []
    failure: set[str] = set()
    illegal: set[str] = set()
    for value in values:
        if value.isdigit():
            gid = int(value)
            if gid in group_ids:
                gids.append(gid)
            else:
                failure.add(value)
        elif value:
            illegal.add(value)
    return _dedupe_ints(gids), failure, illegal


async def _joined_group_ids(bot: Bot) -> set[int]:
    return {int(group["group_id"]) for group in await get_group_list(bot)}


def _dedupe_ints(values: list[int]) -> list[int]:
    return list(dict.fromkeys(values))
