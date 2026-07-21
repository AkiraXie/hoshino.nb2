import asyncio
import random
import time

from pytz import timezone
from sqlalchemy import select

from hoshino.command import UniMessage
from hoshino.core.hooks import on_post_startup
from hoshino.platform import (
    dump_target,
    group_target,
    load_target_or_group,
    send_to_target,
)
from hoshino.platform.depends import GroupID, ParamText
from hoshino.util import send_group_segments, send_segments

from ..utils import PostQueue, UIDManager
from .utils import (
    BiliBiliDynamic,
    Session,
    get_dynamic,
    get_new_dynamic,
    sv,
)
from .utils import (
    DynamicDB as db,
)

# 使用统一的组件
dyn_queue = PostQueue[BiliBiliDynamic]()
uid_manager = UIDManager()

tz = timezone("Asia/Shanghai")


add_dynamic_cmd = sv.on_command(
    "添加动态",
    aliases=("订阅动态", "新增动态", "动态订阅", "adddyn"),
    compact=False,
)


@add_dynamic_cmd.handle()
async def _(gid: int | None = GroupID(), uid: str = ParamText()):
    if gid is None:
        await UniMessage.text("请在群聊中使用").send()
        return
    target_data = dump_target(group_target(gid))
    try:
        dyn = await get_new_dynamic(uid)
        if not dyn:
            await UniMessage.text(f"无法添加 {uid}").send()
            return
    except Exception as e:
        sv.logger.exception(e)
        await UniMessage.text(f"UID {uid} 信息获取失败").send()
        return
    uid_int = dyn.uid
    ts = time.time()
    name = dyn.nickname
    with Session() as session:
        stmt = select(db).where(db.group == gid, db.uid == uid_int)
        obj = session.execute(stmt).scalar_one_or_none()
        if obj:
            obj.time = ts
            obj.name = name
            obj.target_data = target_data
        else:
            obj = db(
                group=gid,
                uid=uid_int,
                time=ts,
                name=name,
                target_data=target_data,
            )
            session.add(obj)
        session.commit()
    await uid_manager.add_uid(dyn.uid)
    await UniMessage.text(f"{name} 订阅动态成功").send()


remove_dynamic_cmd = sv.on_command(
    "删除订阅动态",
    aliases=("取消订阅动态", "关闭订阅动态", "删除动态", "取消动态", "deldyn"),
)


@remove_dynamic_cmd.handle()
async def _(gid: int | None = GroupID(), uid: str = ParamText()):
    if gid is None:
        await UniMessage.text("请在群聊中使用").send()
        return
    with Session() as session:
        if uid.isdecimal():
            uid_int = uid
            stmt = select(db).where(db.group == gid, db.uid == uid_int)
            rows = session.execute(stmt).scalars().all()
            for row in rows:
                session.delete(row)
            num = len(rows)
            session.commit()
            if num:
                await uid_manager.remove_uid(
                    uid,
                    lambda u: bool(
                        session.execute(
                            select(db).where(db.uid == u)
                        ).scalar_one_or_none()
                    ),
                )
        else:
            stmt = select(db).where(db.group == gid, db.name == uid)
            rows = session.execute(stmt).scalars().all()
            if rows:
                target_uid = rows[0].uid
                for row in rows:
                    session.delete(row)
                num = len(rows)
                session.commit()
                if num:
                    await uid_manager.remove_uid(
                        str(target_uid),
                        lambda u: bool(
                            session.execute(
                                select(db).where(db.uid == int(u))
                            ).scalar_one_or_none()
                        ),
                    )
            else:
                num = 0
    if num:
        await UniMessage.text(f"{uid} 删除订阅动态成功").send()
    else:
        await UniMessage.text(f"{uid} 删除订阅动态失败").send()


list_dynamic_cmd = sv.on_command(
    "本群动态订阅",
    aliases={"订阅动态列表", "动态订阅列表", "动态列表", "listdyn", "lsdyn"},
)


@list_dynamic_cmd.handle()
async def _(gid: int | None = GroupID()):
    if gid is None:
        await UniMessage.text("请在群聊中使用").send()
        return
    with Session() as session:
        stmt = select(db).where(db.group == gid)
        rows = session.execute(stmt).scalars().all()
    if not rows:
        await UniMessage.text("本群没有订阅动态").send()
    else:
        uids = [str(row.name) for row in rows]
        num = len(uids)
        msg = []
        msg.append(f"本群订阅了{num}个bilibili动态:")
        msg.extend(uids)
        await UniMessage.text("\n".join(msg)).send()


check_dynamic_cmd = sv.on_command(
    "查看最新动态",
    aliases={"看动态", "看最新动态", "查动态", "查看动态", "seedyn", "kkdyn", "kkbl"},
)


@check_dynamic_cmd.handle()
async def _(gid: int | None = GroupID(), arg: str = ParamText()):
    if gid is None:
        await UniMessage.text("请在群聊中使用").send()
        return
    with Session() as session:
        if arg.isdecimal():
            uid_int = arg
            stmt = select(db).where(db.group == gid, db.uid == uid_int)
            rows = session.execute(stmt).scalars().all()
        else:
            stmt = select(db).where(db.group == gid, db.name == arg)
            rows = session.execute(stmt).scalars().all()
    if not rows:
        await UniMessage.text(f"没有订阅{arg}动态").send()
    else:
        uid_int = rows[0].uid
        dyn = await get_new_dynamic(uid_int)
        if not dyn:
            await UniMessage.text(f"没有获取到{arg}动态").send()
            return
        post_message = await dyn.get_message()
        msgs = dyn.render_message(post_message)
        await send_segments(msgs)


# @scheduled_job("interval", seconds=50, jitter=5, id="获取bili动态")
async def get_bili_dyn():
    ready_count = uid_manager.get_count()
    if ready_count == 0:
        return

    uid_str = await uid_manager.get_next_uid()
    if not uid_str:
        return

    success = False
    try:
        uid_int = uid_str
        with Session() as session:
            stmt = select(db).where(db.uid == uid_int)
            rows = session.execute(stmt).scalars().all()
        if not rows:
            await uid_manager.remove_uid(
                uid_str,
                lambda u: bool(
                    Session()
                    .execute(select(db).where(db.uid == u))
                    .scalar_one_or_none()
                ),
            )
            return

        time_rows = sorted(rows, key=lambda x: x.time, reverse=True)
        min_ts = time_rows[0].time
        dyns = await get_dynamic(uid_str, min_ts)
        if not dyns:
            success = True
            return

        max_timestamp = max(dyn.timestamp for dyn in dyns)
        for dyn in dyns:
            dyn.timestamp = max_timestamp
            b = dyn_queue.put(dyn)
            if b:
                sv.logger.info(
                    f"获取到新的动态: {dyn.nickname} ({dyn.url} {dyn.timestamp})"
                )
        success = True

        if ready_count > 1:
            return
        else:
            await asyncio.sleep(0.5)

    except Exception as e:
        sv.logger.error(f"获取Bili动态失败 UID {uid_str}: {e}")
        success = False
    finally:
        await uid_manager.finish_processing(uid_str, success)


async def handle_bili_dyn(dyn: BiliBiliDynamic, sem):
    async with sem:
        sv.logger.info(f"推送新动态: {dyn.nickname} ({dyn.url} {dyn.timestamp})")
        uid = dyn.uid
        with Session() as session:
            stmt = select(db).where(db.uid == uid)
            rows = session.execute(stmt).scalars().all()
        rows_by_group = {row.group: row for row in rows}
        _gids = list(rows_by_group)
        await asyncio.sleep(random.uniform(1, 5))
        groups = await sv.get_enable_groups()
        gids = list(filter(lambda x: x in groups, _gids))
        if not gids:
            for gid in _gids:
                await asyncio.sleep(0.1)
                with Session() as session:
                    stmt = select(db).where(db.uid == uid, db.group == gid)
                    obj = session.execute(stmt).scalar_one_or_none()
                    if obj:
                        obj.time = dyn.timestamp
                        obj.name = dyn.nickname
                        session.commit()
            dyn_queue.remove_id(dyn.id)
            await asyncio.sleep(0.5)
            return
        post_message = await dyn.get_message()
        msgs = dyn.render_message(post_message)
        for gid in gids:
            await asyncio.sleep(random.uniform(2, 5))
            bot = groups[gid][0]
            target = load_target_or_group(rows_by_group[gid].target_data, gid)
            with Session() as session:
                stmt = select(db).where(db.uid == uid, db.group == gid)
                obj = session.execute(stmt).scalar_one_or_none()
                if obj:
                    obj.time = dyn.timestamp
                    obj.name = dyn.nickname
                    session.commit()
            try:
                if msgs:
                    m = msgs[0]
                    await send_to_target(bot, target, m)
                    await asyncio.sleep(random.uniform(0, 0.5))
                    await send_group_segments(bot, gid, msgs[1:])
            except Exception as e:
                sv.logger.error(f"发送 bili 动态失败: {e}")
        dyn_queue.remove_id(dyn.id)


async def bili_dyn_dispatcher():
    sem = asyncio.Semaphore(5)
    while True:
        dyn = dyn_queue.get()
        if not dyn:
            await asyncio.sleep(0.5)
            continue
        asyncio.create_task(handle_bili_dyn(dyn, sem))


@on_post_startup
async def start_bili_dyn_dispatcher():
    with Session() as session:
        stmt = select(db.uid).distinct()
        uids = session.scalars(stmt).all()
    await uid_manager.init(uids)
    asyncio.create_task(bili_dyn_dispatcher())
