import asyncio
from collections import defaultdict
from typing import List
from hoshino.schedule import scheduled_job
from hoshino import Service, Bot, Event, MessageSegment
from datetime import datetime
from hoshino.typing import FinishedException
from .utils import (
    Dynamic,
    DynamicDB as db,
    LiveDB,
    get_dynamic,
    get_live_status,
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
        def remove_id(self,id: int) -> None:
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


@sv.on_command("删除订阅动态", aliases=("取消订阅动态", "关闭订阅动态", "删除动态", "取消动态"))
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


@sv.on_command("本群动态订阅", aliases={"订阅动态列表", "动态订阅列表", "动态列表"})
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


@sv.on_command("查看最新动态",aliases={'看动态','看最新动态','查动态',"查看动态"})
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
        msg = await dyn.get_message(sv.logger)
        await bot.send(event, msg)


@scheduled_job("interval", seconds=135, jitter=5, id="获取bili动态")
async def get_bili_dyn():
    uids = [row.uid for row in db.select(db.uid).distinct()]
    if not uids:
        await asyncio.sleep(0.5)
        return
    for uid in uids:
        rows : List[db] = db.select().where(db.uid == uid)
        if not rows:
            continue
        time_rows = sorted(rows,key=lambda x:x.time,reverse=True)
        min_ts = time_rows[0].time
        dyns = await get_dynamic(uid, min_ts)
        for dyn in dyns:
            dyn_queue.put(dyn)
        await asyncio.sleep(2)
    await asyncio.sleep(0.5)

@scheduled_job("interval", seconds=30, jitter=10, id="推送bili动态")
async def push_bili_dyn():
    groups = await sv.get_enable_groups()
    dyn = dyn_queue.get()
    if not dyn:
        await asyncio.sleep(0.5)
        return
    uid = dyn.uid
    rows : List[db] = db.select().where(db.uid == uid)
    _gids = [row.group for row in rows]
    gids = list(filter(lambda x: x in groups,_gids))
    if not gids:
        for gid in _gids:
            await asyncio.sleep(0.1) 
            db.replace(group=gid, uid=uid, time=dyn.time, name=dyn.name).execute()
        dyn_queue.remove_id(dyn.id)
        await asyncio.sleep(0.5)
        return
    msg = await dyn.get_message(sv.logger)
    for gid in gids:
        await asyncio.sleep(0.35) 
        bot = groups[gid][0]
        db.replace(group=gid, uid=uid, time=dyn.time, name=dyn.name).execute()
        try:
            await bot.send_group_msg(group_id=gid,message=msg)
        except Exception as e:
            sv.logger.error(f"发送 bili 动态失败: {e}") 
    dyn_queue.remove_id(dyn.id)
    await asyncio.sleep(0.5)            


status_dic = {0: "未开播", 1: "直播中"}
live_state = defaultdict(int)
live_times = defaultdict(int)

@sv.on_command("订阅直播", aliases=("添加直播", "直播订阅"))
async def _(bot: Bot, event: Event):
    def get_uid_status(uid, dic):
        uid = str(uid)
        info = dic[uid]
        status = 0 if info["live_status"] == 2 else info["live_status"]
        desc = f"{info['uname']} {status_dic[status]}"
        if status == 1:
            dt=datetime.utcnow()-datetime.utcfromtimestamp(info['live_time'])
            desc += f"\n直播时长:{int(dt.total_seconds()//3600)}小时{int(dt.total_seconds()%3600//60)}分{int(dt.total_seconds()%60)}秒"
            live_times[uid]=info['live_time']
        live_state[uid] = status
        return desc
    gid = event.group_id
    uid = event.get_plaintext()
    try:
        uid = int(uid)
        name = await get_user_name(uid)
    except Exception as e:
        sv.logger.exception(e)
        await bot.send(event, f"UID {uid} 不合法")
    dic = await get_live_status([uid])
    desc = get_uid_status(uid, dic)
    await bot.send(event, f"{name} 直播订阅成功")
    await bot.send(event, desc)
    LiveDB.replace(uid=uid, name=name, group=gid).execute()


@sv.on_command("本群直播订阅", aliases={"直播列表", "订阅直播列表", "直播订阅列表"})
async def _(bot: Bot, event: Event):
    gid = event.group_id
    rows = LiveDB.select().where(LiveDB.group == gid).execute()
    if not rows:
        await bot.send(event, "本群没有订阅直播")
    else:
        uids = [str(row.uid) for row in rows]
        infos = await get_live_status(uids)
        msgs = []
        num = len(uids)
        msgs.append(f"本群订阅了{num}个bilibili直播:")
        for uid in uids:
            info = infos[uid]
            name = info["uname"]
            status = 0 if info["live_status"] == 2 else info["live_status"]
            live_state[uid] = status
            desc = status_dic[status]
            if status == 1:
                dt=datetime.utcnow()-datetime.utcfromtimestamp(info['live_time'])
                desc += f"\n直播时长:{int(dt.total_seconds()//3600)}小时{int(dt.total_seconds()%3600//60)}分{int(dt.total_seconds()%60)}秒"
                live_times[uid]=info['live_time']            
            room_id = info["short_id"] if info["short_id"] else info["room_id"]
            url = "https://live.bilibili.com/" + str(room_id)
            msgs.append(f"{name} 状态:{desc}\n{url}")
        await bot.send(event, "\n".join(msgs))


@sv.on_command("取消订阅直播", aliases=("关闭直播订阅", "删除直播", "取消直播"))
async def _(bot: Bot, event: Event):
    gid = event.group_id
    uid = event.get_plaintext()
    if uid.isdecimal():
        uid = int(uid)
        rows = LiveDB.delete().where(LiveDB.uid == uid, LiveDB.group == gid).execute()
    else:
        rows = LiveDB.delete().where(LiveDB.name == uid, LiveDB.group == gid).execute()
    if rows:
        await bot.send(event, f"{uid} 取消订阅直播成功")
    else:
        await bot.send(event, f"{uid} 取消订阅直播失败")


@scheduled_job("interval", seconds=30, jitter=3, id="推送bili直播")
async def _():
    groups = await sv.get_enable_groups()
    uids = [row.uid for row in LiveDB.select(LiveDB.uid).distinct()]
    if not uids:
        return
    dic = await get_live_status(uids)
    need_send = {}
    for uid in dic:
        info = dic[str(uid)]
        status = 0 if info["live_status"] == 2 else info["live_status"]

        if status == live_state[str(uid)]:
            continue
        elif status == 0:
            name = info["uname"]
            live_msg = f"{name} 下播了！"
            if live_times[uid]!=0:
                dt=datetime.utcnow()-datetime.utcfromtimestamp(live_times[uid])
                live_msg+=f"\n直播时长:{int(dt.total_seconds()//3600)}小时{int(dt.total_seconds()%3600//60)}分{int(dt.total_seconds()%60)}秒"
            need_send[uid] = live_msg
            live_state[uid] = status
            live_times[uid]= 0
        else:
            room_id = info["short_id"] if info["short_id"] else info["room_id"]
            url = "https://live.bilibili.com/" + str(room_id)
            name = info["uname"]
            title = info["title"]
            cover = (
                info["cover_from_user"] if info["cover_from_user"] else info["keyframe"]
            )
            live_msg = (
                f"开播啦！ {name}\n{title}\n" + MessageSegment.image(cover) + f"\n{url}"
            )
            need_send[uid] = live_msg
            live_state[uid] = status
            live_times[uid]=info['live_time']
    if need_send:
        for uid in need_send:
            gids = [
                row.group
                for row in LiveDB.select(LiveDB.group).where(LiveDB.uid == int(uid))
            ]
            gids = [gid for gid in groups if gid in gids]
            if gids:
                for gid in gids:
                    bot = groups[gid][0]
                    await bot.send_group_msg(group_id=gid, message=need_send[uid])
                    await asyncio.sleep(0.6)


from nonebot import get_driver
from hoshino.util import send_to_superuser

startup = get_driver().on_bot_connect


@startup
async def _(bot: Bot):
    uids = [row.uid for row in LiveDB.select(LiveDB.uid).distinct()]
    dic = await get_live_status(uids)
    msgs = []
    num = len(uids)
    msgs.append(f"共订阅了{num}个bilibili直播:")
    for uid in uids:
        uid = str(uid)
        info = dic[uid]
        name = info["uname"]
        status = 0 if info["live_status"] == 2 else info["live_status"]
        live_state[uid] = status
        desc = status_dic[status]
        if status == 1:
            dt=datetime.utcnow()-datetime.utcfromtimestamp(info['live_time'])
            desc += f"\n直播时长:{int(dt.total_seconds()//3600)}小时{int(dt.total_seconds()%3600//60)}分{int(dt.total_seconds()%60)}秒"
            live_times[uid]=info['live_time']
        room_id = info["short_id"] if info["short_id"] else info["room_id"]
        url = "https://live.bilibili.com/" + str(room_id)
        msgs.append(f"{name} 状态:{desc}\n{url}")
    await asyncio.sleep(0.5)
    await send_to_superuser(bot, "\n".join(msgs))
