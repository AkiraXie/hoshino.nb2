import asyncio
import random
import time

from sqlalchemy import select

from hoshino.command import UniMessage
from hoshino.core.hooks import on_post_startup, on_shutdown, spawn
from hoshino.platform import (
    dump_target,
    group_target,
    load_target_or_group,
    send_to_target,
)
from hoshino.platform.depends import GroupID, ParamText
from hoshino.util.message import send_group_segments, send_segments

from ..utils import PostQueue, UIDManager
from .utils import (
    BiliBiliDynamic,
    Session,
    get_dynamic,
    get_new_dynamic,
    sv,
)
from .utils import (
    DynamicDB as db,  # noqa: N813  # 表模型短别名，查询语句中作为表引用
)

# 使用统一的组件
dyn_queue = PostQueue[BiliBiliDynamic]()
uid_manager = UIDManager()

# 后台任务引用：bili_dyn_dispatcher 循环 worker，shutdown 时取消
_dyn_dispatcher_task: asyncio.Task | None = None


def _uid_still_subscribed(uid: str) -> bool:
    """remove_uid 回调：uid 是否仍被任何群订阅。

    使用独立 Session 查询，避免 lambda 捕获 with 块内的 session。
    """
    with Session() as session:
        stmt = select(db).where(db.uid == uid)
        return session.execute(stmt).scalar_one_or_none() is not None


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
    except Exception:
        sv.logger.exception(f"获取 UID {uid} 信息失败", exception=True)
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
                await uid_manager.remove_uid(uid, _uid_still_subscribed)
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
                    await uid_manager.remove_uid(str(target_uid), _uid_still_subscribed)
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
            await uid_manager.remove_uid(uid_str, _uid_still_subscribed)
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
                sv.logger.info(f"获取到新的动态: {dyn.nickname} ({dyn.url} {dyn.timestamp})")
        success = True

        if ready_count > 1:
            return
        await asyncio.sleep(0.5)

    except Exception:
        sv.logger.exception(f"获取Bili动态失败 UID {uid_str}", exception=True)
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
            except Exception:
                sv.logger.exception(f"发送 bili 动态失败: 群{gid}", exception=True)
        dyn_queue.remove_id(dyn.id)


async def bili_dyn_dispatcher():
    sem = asyncio.Semaphore(5)
    while True:
        dyn = dyn_queue.get()
        if not dyn:
            await asyncio.sleep(0.5)
            continue
        spawn(handle_bili_dyn(dyn, sem))


@on_post_startup
async def start_bili_dyn_dispatcher():
    global _dyn_dispatcher_task
    with Session() as session:
        stmt = select(db.uid).distinct()
        uids = session.scalars(stmt).all()
    await uid_manager.init(uids)
    _dyn_dispatcher_task = spawn(bili_dyn_dispatcher())


@on_shutdown
async def stop_bili_dyn_dispatcher():
    if _dyn_dispatcher_task:
        _dyn_dispatcher_task.cancel()
