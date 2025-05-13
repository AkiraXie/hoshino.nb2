import asyncio
from datetime import datetime
from typing import List
import random
from hoshino import Bot, Event, on_startup
from hoshino.schedule import scheduled_job
from hoshino.typing import FinishedException
from .utils import get_sub_list, sv, WeiboDB as db, Post, get_sub_new
from asyncio import Queue
import re


class PostQueue(Queue):
    def __init__(self, maxsize: int = 0) -> None:
        super().__init__(maxsize)
        self._set = set()

    def put(self, item: Post) -> bool:
        if item.id not in self._set:
            self._set.add(item.id)
            super().put_nowait(item)
            loop = asyncio.get_event_loop()
            loop.call_later(3600, self._set.discard, item.id)
            return True
        return False

    def get(self) -> Post:
        if self.empty():
            return None
        item = super().get_nowait()
        return item

    def remove_id(self, id: str) -> None:
        self._set.discard(id)


weibo_queue = PostQueue()


@sv.on_command(
    "添加微博订阅",
    aliases=("订阅微博", "新增微博", "添加微博", "添加weibo", "addweibo", "addwb"),
)
async def add_subscription(bot: Bot, event: Event):
    gid = event.group_id
    msg = event.get_plaintext().strip()
    keywords = []
    try:
        msg = msg.split(" ")
        if len(msg) == 1:
            uid = msg[0]
        else:
            uid = msg[0]
            keywords = msg[1:]
        if not uid.isdecimal():
            match = re.search(r"weibo\.com/u/(\d+)", uid)
            if match:
                uid = match.group(1)
            else:
                await bot.send(
                    event, "无效的UID格式，请输入数字ID或完整的微博个人主页链接"
                )
                raise FinishedException
        post = await get_sub_new(uid, 0, keywords=keywords)
        if not post:
            post = await get_sub_new(uid, 0)
    except Exception as e:
        sv.logger.exception(e)
        await bot.send(event, f"无法获取微博用户信息，UID: {uid}")
        raise FinishedException
    kw = "-_-".join(keywords) if keywords else ""
    db.replace(
        group=gid, uid=uid, name=post.nickname, time=post.timestamp, keyword=kw
    ).execute()
    if keywords:
        await bot.send(
            event, f"成功订阅微博用户：{post.nickname} UID: {uid} 关键词: {kw}"
        )
    else:
        await bot.send(event, f"成功订阅微博用户：{post.nickname} UID: {uid}")


@sv.on_command(
    "删除微博订阅", aliases=("取消微博", "删除微博", "rmweibo", "删除weibo", "rmwb")
)
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


@sv.on_command("微博订阅", aliases=("微博订阅列表", "lookweibo", "lswb", "listweibo"))
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


@sv.on_command("微博最新订阅", aliases=("查看微博最新", "seeweibo", "kkwb"))
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
        keywords = rows[0].keyword
        if keywords:
            keywords = keywords.split("-_-")
        else:
            keywords = []
        post = await get_sub_new(uid, 0, keywords=keywords)
        msg = await post.get_msg_with_screenshot()
        if not msg:
            await bot.send(event, f"没有获取到{arg}微博")
            return
        else:
            for m in msg:
                await bot.send(event, m)
                await asyncio.sleep(0.25)


@scheduled_job("interval", seconds=114, id="获取微博更新", jitter=5)
@on_startup
async def fetch_weibo_updates():
    uids = [row.uid for row in db.select(db.uid).distinct()]
    if not uids:
        await asyncio.sleep(0.5)
        return
    for uid in uids:
        rows: List[db] = db.select().where(db.uid == uid).execute()
        if not rows:
            continue
        time_rows = sorted(rows, key=lambda x: x.time, reverse=True)
        min_ts = time_rows[0].time
        kw = time_rows[0].keyword
        if kw:
            kw = kw.split("-_-")
        else:
            kw = []
        try:
            dyns = await get_sub_list(uid, min_ts, kw)
            for dyn in dyns:
                b = weibo_queue.put(dyn)
                if b:
                    sv.logger.info(
                        f"获取到微博更新: {dyn.id} {dyn.nickname} {dyn.timestamp} {dyn.url}"
                    )
            await asyncio.sleep(0.3)
        except Exception as e:
            sv.logger.error(f"获取微博更新失败: {e}")
            await asyncio.sleep(0.3)
            continue
    await asyncio.sleep(0.5)


@scheduled_job("interval", seconds=20, id="推送微博更新", jitter=5)
async def push_weibo_updates():
    groups = await sv.get_enable_groups()
    dyn = weibo_queue.get()
    if not dyn:
        await asyncio.sleep(0.5)
        return
    sv.logger.info(f"推送微博更新: {dyn.id} {dyn.nickname} {dyn.timestamp} {dyn.url}")
    uid = dyn.uid
    rows: List[db] = db.select().where(db.uid == uid)
    _gids = [row.group for row in rows]
    gids = list(filter(lambda x: x in groups, _gids))
    if not gids:
        for gid in _gids:
            await asyncio.sleep(0.1)
            db.update(time=dyn.timestamp, name=dyn.nickname).where(
                db.uid == uid, db.group == gid
            ).execute()
        weibo_queue.remove_id(dyn.id)
        await asyncio.sleep(0.5)
        return
    msgs = await dyn.get_msg_with_screenshot()
    for gid in gids:
        await asyncio.sleep(0.35)
        bot = groups[gid][0]
        db.update(time=dyn.timestamp, name=dyn.nickname).where(
            db.uid == uid, db.group == gid
        ).execute()
        try:
            for msg in msgs:
                await bot.send_group_msg(group_id=gid, message=msg)
                rand = random.random()
                await asyncio.sleep(rand * 0.5 + 0.1)
        except Exception as e:
            sv.logger.error(f"发送 weibo post 失败: {e}")
    weibo_queue.remove_id(dyn.id)
    await asyncio.sleep(0.5)
