import asyncio
from datetime import datetime
from typing import List
from hoshino import  Bot, Event
from hoshino.schedule import scheduled_job
from hoshino.typing import FinishedException
from .utils import get_sub_list,sv,WeiboDB as db,Post,get_sub_new
from asyncio import Queue
class PostQueue(Queue):
        def __init__(self, maxsize: int = 0) -> None:
            super().__init__(maxsize)
            self._set = set()
        def put(self, item: Post) -> None:
            if item.id not in self._set:
                self._set.add(item.id)
                super().put_nowait(item)
                loop = asyncio.get_event_loop()
                loop.call_later(3600, self._set.discard, item.id)
        def get(self) -> Post:
            if self.empty():
                return None
            item = super().get_nowait()
            return item
        def remove_id(self,id: str) -> None:
            self._set.discard(id)

weibo_queue = PostQueue()


@sv.on_command("添加微博订阅", aliases=("订阅微博", "新增微博","添加微博","添加weibo","addweibo","addwb"))
async def add_subscription(bot: Bot, event: Event):
    gid = event.group_id
    uid = event.get_plaintext().strip()
    try:
        post = await get_sub_new(uid, 0)
    except Exception as e:
        sv.logger.exception(e)
        await bot.send(event, f"无法获取微博用户信息，UID: {uid}")
        raise FinishedException
    db.replace(group=gid, uid=uid, name=post.nickname, time=post.timestamp).execute()
    await bot.send(event, f"成功订阅微博用户：{post.nickname} UID: {uid}")

@sv.on_command("删除微博订阅", aliases=("取消微博", "删除微博","rmweibo","删除weibo","rmwb"))
async def remove_subscription(bot: Bot, event: Event):
    gid = event.group_id
    uid = event.get_plaintext().strip()
    if uid.isdecimal():
        rows = db.delete().where(db.group == gid, db.uid == uid).execute()
    else:
        rows = db.delete().where(db.group == gid, db.name == uid).execute()
    if rows:
        await bot.send(event, f"{uid} 删除微博订阅成功")
    else:
        await bot.send(event, f"{uid} 删除微博订阅失败")

@sv.on_command("微博订阅", aliases=("微博订阅列表", "lookweibo","lswb","listweibo"))
async def list_subscriptions(bot: Bot, event: Event):
    gid = event.group_id
    rows = db.select().where(db.group == gid).execute()
    if not rows:
        await bot.send(event, "本群没有订阅微博用户")
        return
    msg = "当前订阅的微博用户：\n"
    for row in rows:
        uid = row.uid
        name = row.name
        ts = datetime.fromtimestamp(row.time).strftime("%Y-%m-%d %H:%M:%S")
        msg += f"UID: {uid}, 昵称: {name}, 上次更新时间: {ts}\n"
    await bot.send(event, msg)

@sv.on_command("微博最新订阅", aliases=("查看微博最新", "seeweibo","kkwb"))
async def see_weibo(bot: Bot, event: Event):
    gid = event.group_id
    arg = event.get_plaintext().strip()
    if arg.isdecimal():
        rows = db.select().where(db.group == gid, db.uid == arg).execute()
    else:
        rows = db.select().where(db.group == gid, db.name == arg).execute()
    if not rows:
        await bot.send(event, f"没有订阅{arg}微博")
    else:
        uid = rows[0].uid
        post = await get_sub_new(uid, 0)
        msg = await post.get_msg_with_screenshot()
        if not msg:
            await bot.send(event, f"没有获取到{arg}微博")
            return
        else:
            for m in msg:
                await bot.send(event, m)
                await asyncio.sleep(0.25)

@scheduled_job("interval", seconds=114, id="获取微博更新",jitter=5)
async def fetch_weibo_updates():
    uids = [row.uid for row in db.select(db.uid).distinct()]
    if not uids:
        await asyncio.sleep(0.5)
        return
    for uid in uids:
        rows : List[db] = db.select().where(db.uid == uid).execute()
        if not rows:
            continue
        time_rows = sorted(rows,key=lambda x:x.time,reverse=True)
        min_ts = time_rows[0].time
        dyns = await get_sub_list(uid, min_ts)
        for dyn in dyns:
            sv.logger.info(f"获取到微博更新: {dyn.id} {dyn.nickname} {dyn.timestamp} {dyn.url}")
            weibo_queue.put(dyn)
        await asyncio.sleep(2)
    await asyncio.sleep(0.5)

@scheduled_job("interval", seconds=40, id="推送微博更新",jitter=5)
async def push_weibo_updates():
    groups = await sv.get_enable_groups()
    dyn = weibo_queue.get()
    if not dyn:
        await asyncio.sleep(0.5)
        return
    uid = dyn.id
    rows : List[db] = db.select().where(db.uid == uid)
    _gids = [row.group for row in rows]
    gids = list(filter(lambda x: x in groups,_gids))
    if not gids:
        for gid in _gids:
            await asyncio.sleep(0.1) 
            db.replace(group=gid, uid=uid, time=dyn.timestamp, name=dyn.nickname).execute()
        weibo_queue.remove_id(dyn.id)
        await asyncio.sleep(0.5)
        return
    msgs = dyn.get_msg()
    for gid in gids:
        await asyncio.sleep(0.35) 
        bot = groups[gid][0]
        db.replace(group=gid, uid=uid, time=dyn.timestamp, name=dyn.nickname).execute()
        try:
            for msg in msgs:
                await bot.send_group_msg(group_id=gid,message=msg)
                await asyncio.sleep(0.25)   
        except Exception as e:
            sv.logger.error(f"发送 weibo post 失败: {e}") 
    weibo_queue.remove_id(dyn.id)
    await asyncio.sleep(0.5)   