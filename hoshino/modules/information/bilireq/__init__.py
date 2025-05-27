import asyncio
from collections import defaultdict
from typing import List
from hoshino.schedule import scheduled_job
from hoshino import Service, Bot, Event, MessageSegment
from datetime import datetime
from hoshino.typing import FinishedException
from hoshino.util import send, send_group_segments, send_segments
from .utils import (
    Dynamic,
    DynamicDB as db,
    get_dynamic,
    get_new_dynamic,
    get_user_name,
)
from pytz import timezone
from asyncio import Queue


class DynamicQueue(Queue):
    def __init__(self, maxsize: int = 0) -> None:
        super().__init__(maxsize)
        self._set = set()

    def put(self, item: Dynamic) -> None:
        if item.id not in self._set:
            self._set.add(item.id)
            super().put_nowait(item)
            loop = asyncio.get_event_loop()
            loop.call_later(3600, self._set.discard, item.id)

    def get(self) -> Dynamic:
        if self.empty():
            return None
        item = super().get_nowait()
        return item

    def remove_id(self, id: int) -> None:
        self._set.discard(id)


dyn_queue = DynamicQueue()

sv = Service("bilireq", enable_on_default=False)
tz = timezone("Asia/Shanghai")


@sv.on_command("添加动态", aliases=("订阅动态", "新增动态", "动态订阅"))
async def _(bot: Bot, event: Event):
    gid = event.group_id
    uid = event.get_plaintext()
    try:
        uid = int(uid)
        name = await get_user_name(uid)
    except Exception as e:
        sv.logger.exception(e)
        await bot.send(event, f"UID {uid} 不合法")
        raise FinishedException
    ts = datetime.now(tz).timestamp()
    db.replace(group=gid, uid=uid, time=ts, name=name).execute()
    await bot.send(event, f"{name} 订阅动态成功")


@sv.on_command(
    "删除订阅动态",
    aliases=("取消订阅动态", "关闭订阅动态", "删除动态", "取消动态", "adddyn"),
)
async def _(bot: Bot, event: Event):
    gid = event.group_id
    uid = event.get_plaintext()
    if uid.isdecimal():
        uid = int(uid)
        rows = db.delete().where(db.group == gid, db.uid == uid).execute()
    else:
        rows = db.delete().where(db.group == gid, db.name == uid).execute()
    if rows:
        await bot.send(event, f"{uid} 删除订阅动态成功")
    else:
        await bot.send(event, f"{uid} 删除订阅动态失败")


@sv.on_command(
    "本群动态订阅",
    aliases={"订阅动态列表", "动态订阅列表", "动态列表", "listdyn", "lsdyn"},
)
async def _(bot: Bot, event: Event):
    gid = event.group_id
    rows = db.select().where(db.group == gid).execute()
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
    if arg.isdecimal():
        uid = int(arg)
        rows = db.select().where(db.group == gid, db.uid == uid)
    else:
        rows = db.select().where(db.group == gid, db.name == arg)
    if not rows:
        await bot.send(event, f"没有订阅{arg}动态")
    else:
        uid = rows[0].uid
        dyn = await get_new_dynamic(uid)
        msgs = await dyn.get_message()
        await send_segments(msgs)


@scheduled_job("interval", seconds=245, jitter=15, id="获取bili动态")
async def get_bili_dyn():
    uids = [row.uid for row in db.select(db.uid).distinct()]
    if not uids:
        await asyncio.sleep(0.5)
        return
    for uid in uids:
        rows: List[db] = db.select().where(db.uid == uid)
        if not rows:
            continue
        time_rows = sorted(rows, key=lambda x: x.time, reverse=True)
        min_ts = time_rows[0].time
        dyns = await get_dynamic(uid, min_ts)
        for dyn in dyns:
            sv.logger.info(f"获取到新的动态: {dyn.name} ({dyn.url} {dyn.time})")
            dyn_queue.put(dyn)
        await asyncio.sleep(2)
    await asyncio.sleep(0.5)


@scheduled_job("interval", seconds=75, jitter=10, id="推送bili动态")
async def push_bili_dyn():
    groups = await sv.get_enable_groups()
    dyn = dyn_queue.get()
    if not dyn:
        await asyncio.sleep(0.5)
        return
    sv.logger.info(f"推送新动态: {dyn.name} ({dyn.url} {dyn.time})")
    uid = dyn.uid
    rows: List[db] = db.select().where(db.uid == uid)
    _gids = [row.group for row in rows]
    gids = list(filter(lambda x: x in groups, _gids))
    if not gids:
        for gid in _gids:
            await asyncio.sleep(0.1)
            db.replace(group=gid, uid=uid, time=dyn.time, name=dyn.name).execute()
        dyn_queue.remove_id(dyn.id)
        await asyncio.sleep(0.5)
        return
    msgs = await dyn.get_message(False)
    for gid in gids:
        await asyncio.sleep(0.35)
        bot = groups[gid][0]
        db.replace(group=gid, uid=uid, time=dyn.time, name=dyn.name).execute()
        try:
            await send_group_segments(bot, gid, msgs)
        except Exception as e:
            sv.logger.error(f"发送 bili 动态失败: {e}")
    dyn_queue.remove_id(dyn.id)
    await asyncio.sleep(0.5)
