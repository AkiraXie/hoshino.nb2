import asyncio
import time
from hoshino.schedule import scheduled_job
from hoshino import Service, Bot, Event, on_startup
import random
from hoshino.util import send_group_segments, send_segments
from .utils import (
    BiliBiliDynamic,
    DynamicDB as db,
    get_dynamic,
    get_new_dynamic,
    Session,
)
from ..utils import PostQueue, UIDManager
from pytz import timezone
from sqlalchemy import select

# 使用统一的组件
dyn_queue = PostQueue[BiliBiliDynamic]()
uid_manager = UIDManager()
sv = Service("bilireq", enable_on_default=False)
tz = timezone("Asia/Shanghai")


@sv.on_command("添加动态", aliases=("订阅动态", "新增动态", "动态订阅"))
async def _(bot: Bot, event: Event):
    gid = event.group_id
    uid = event.get_plaintext()
    try:
        dyn = await get_new_dynamic(uid)
        if not dyn:
            await bot.send(event, f"无法添加 {uid}")
            return
    except Exception as e:
        sv.logger.exception(e)
        await bot.send(event, f"UID {uid} 不合法")
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
        else:
            obj = db(group=gid, uid=uid_int, time=ts, name=name)
            session.add(obj)
        session.commit()
    await uid_manager.add_uid(dyn.uid)
    await bot.send(event, f"{name} 订阅动态成功")


@sv.on_command(
    "删除订阅动态",
    aliases=("取消订阅动态", "关闭订阅动态", "删除动态", "取消动态", "adddyn"),
)
async def _(bot: Bot, event: Event):
    gid = event.group_id
    uid = event.get_plaintext()
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
        await bot.send(event, f"{uid} 删除订阅动态成功")
    else:
        await bot.send(event, f"{uid} 删除订阅动态失败")


@sv.on_command(
    "本群动态订阅",
    aliases={"订阅动态列表", "动态订阅列表", "动态列表", "listdyn", "lsdyn"},
)
async def _(bot: Bot, event: Event):
    gid = event.group_id
    with Session() as session:
        stmt = select(db).where(db.group == gid)
        rows = session.execute(stmt).scalars().all()
    if not rows:
        await bot.send(event, "本群没有订阅动态")
    else:
        uids = [str(row.name) for row in rows]
        num = len(uids)
        msg = []
        msg.append(f"本群订阅了{num}个bilibili动态:")
        msg.extend(uids)
        await bot.send(event, "\n".join(msg))


@sv.on_command(
    "查看最新动态",
    aliases={"看动态", "看最新动态", "查动态", "查看动态", "seedyn", "kkdyn", "kkbl"},
)
async def _(bot: Bot, event: Event):
    gid = event.group_id
    arg = event.get_plaintext()
    with Session() as session:
        if arg.isdecimal():
            uid_int = arg
            stmt = select(db).where(db.group == gid, db.uid == uid_int)
            rows = session.execute(stmt).scalars().all()
        else:
            stmt = select(db).where(db.group == gid, db.name == arg)
            rows = session.execute(stmt).scalars().all()
    if not rows:
        await bot.send(event, f"没有订阅{arg}动态")
    else:
        uid_int = rows[0].uid
        dyn = await get_new_dynamic(uid_int)
        if not dyn:
            await bot.send(event, f"没有获取到{arg}动态")
            return
        msgs = await dyn.get_message()
        await send_segments(msgs)


@scheduled_job("interval", seconds=1, jitter=0.2, id="获取bili动态")
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
        _gids = [row.group for row in rows]
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
        msgs = await dyn.get_message()
        for gid in gids:
            await asyncio.sleep(random.uniform(2, 5))
            bot = groups[gid][0]
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
                    await bot.send_group_msg(group_id=gid, message=m)
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


@on_startup
async def start_bili_dyn_dispatcher():
    with Session() as session:
        stmt = select(db.uid).distinct()
        uids = session.scalars(stmt).all()
    await uid_manager.init(uids)
    asyncio.create_task(bili_dyn_dispatcher())
