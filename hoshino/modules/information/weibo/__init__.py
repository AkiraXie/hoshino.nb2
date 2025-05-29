# Thanks to https://github.com/MountainDash/nonebot-bison

import asyncio
from datetime import datetime
from typing import List, Set
from hoshino import Bot, Event, on_startup
from hoshino.schedule import scheduled_job
from hoshino.util import send_group_segments, send_segments
from hoshino.typing import FinishedException
from .utils import (
    get_sub_list,
    sv,
    WeiboDB as db,
    Post,
    get_sub_new,
)
from asyncio import Queue
from nonebot.permission import SUPERUSER
import re
import random


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


class UidManager:
    def __init__(self):
        self._uids: Set[str] = set()
        self._uid_queue = asyncio.Queue()
        self._lock = asyncio.Lock()
        self._processing_uids: Set[str] = set()  # 正在处理的 UID

    async def init_from_db(self):
        """从数据库初始化 UID 列表"""
        async with self._lock:
            uids = [row.uid for row in db.select(db.uid).distinct()]
            self._uids = set(uids)
            # 清空队列并重新填充
            while not self._uid_queue.empty():
                try:
                    self._uid_queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
            for uid in self._uids:
                await self._uid_queue.put(uid)
            sv.logger.info(f"初始化 UID 列表，共 {len(self._uids)} 个")

    async def add_uid(self, uid: str):
        """添加 UID"""
        async with self._lock:
            if uid not in self._uids:
                self._uids.add(uid)
                await self._uid_queue.put(uid)
                sv.logger.info(f"添加 UID: {uid}")

    async def remove_uid(self, uid: str):
        """删除 UID（如果该 UID 没有其他群订阅）"""
        # 检查是否还有其他群订阅此 UID
        rows = db.select().where(db.uid == uid).execute()
        if not rows:
            async with self._lock:
                if uid in self._uids:
                    self._uids.remove(uid)
                    self._processing_uids.discard(uid)  # 同时从处理列表移除
                    sv.logger.info(f"删除 UID: {uid}")

    async def get_next_uid(self) -> str:
        """获取下一个要检查的 UID"""
        max_attempts = len(self._uids) if self._uids else 1
        attempts = 0
        
        while attempts < max_attempts:
            if self._uid_queue.empty():
                return None

            uid = await self._uid_queue.get()

            async with self._lock:
                if uid in self._uids and uid not in self._processing_uids:
                    # UID 有效且未在处理中
                    self._processing_uids.add(uid)
                    await self._uid_queue.put(uid)  # 重新放入队列
                    return uid
                elif uid in self._uids:
                    # UID 有效但正在处理中，跳过并重新放入队列
                    await self._uid_queue.put(uid)
                    attempts += 1
                else:
                    # UID 已被删除，跳过
                    attempts += 1
        
        return None

    async def finish_processing(self, uid: str):
        """标记 UID 处理完成"""
        async with self._lock:
            self._processing_uids.discard(uid)

    def get_count(self) -> int:
        """获取 UID 总数"""
        return len(self._uids)


uid_manager = UidManager()


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
            match = re.search(r"weibo\.com\/(u\/)?(\d+)", uid)
            if match:
                uid = match.group(2)
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

    # 同步更新全局 UID 列表
    await uid_manager.add_uid(uid)

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
        # 同步更新全局 UID 列表
        if rows:
            await uid_manager.remove_uid(uid)
    else:
        # 先获取 UID 再删除
        rows = db.select().where(db.group == gid, db.name == uid).execute()
        if rows:
            target_uid = rows[0].uid
            deleted_rows = db.delete().where(db.group == gid, db.name == uid).execute()
            if deleted_rows:
                await uid_manager.remove_uid(target_uid)
        else:
            deleted_rows = 0
        rows = deleted_rows
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
    for i, row in enumerate(rows):
        uid = row.uid
        name = row.name
        ts = datetime.fromtimestamp(row.time).strftime("%Y-%m-%d %H:%M:%S")
        msg += f"{i + 1}. UID: {uid}, 昵称: {name}, 上次更新时间: {ts}\n"
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
        msg = await post.get_msg()
        if not msg:
            await bot.send(event, f"没有获取到{arg}微博")
            return
        else:
            m = msg[0]
            await bot.send(event, m)
            await asyncio.sleep(0.2)
            await send_segments(message=msg[1:])


@scheduled_job("interval", seconds=4, id="获取微博更新", jitter=1)
async def fetch_weibo_updates():
    uid_count = uid_manager.get_count()
    if uid_count == 0:
        await asyncio.sleep(1)
        return

    uid = await uid_manager.get_next_uid()
    if not uid:
        await asyncio.sleep(1)
        return

    try:
        rows: List[db] = db.select().where(db.uid == uid).execute()
        if not rows:
            # UID 已无订阅，从管理器中移除
            await uid_manager.remove_uid(uid)
            return

        time_rows = sorted(rows, key=lambda x: x.time, reverse=True)
        min_ts = time_rows[0].time
        kw = time_rows[0].keyword
        if kw:
            kw = kw.split("-_-")
        else:
            kw = []

        dyns = await get_sub_list(uid, min_ts, kw)
        if not dyns:
            return
        max_timestamp = max(dyn.timestamp for dyn in dyns)
        for dyn in dyns:
            dyn.timestamp = max_timestamp
            b = weibo_queue.put(dyn)
            if b:
                sv.logger.info(
                    f"获取到微博更新: {dyn.uid} {dyn.nickname} {dyn.timestamp} {dyn.url}"
                )
    except Exception as e:
        sv.logger.error(f"获取微博更新失败 UID {uid}: {e}")
    finally:
        # 无论成功失败都要标记处理完成
        await uid_manager.finish_processing(uid)


async def handle_weibo_dyn(dyn: Post, sem: asyncio.Semaphore):
    async with sem:
        sv.logger.info(
            f"推送微博更新: {dyn.uid} {dyn.nickname} {dyn.timestamp} {dyn.url}"
        )
        uid = dyn.uid
        rows: List[db] = db.select().where(db.uid == uid)
        _gids = [row.group for row in rows]
        await asyncio.sleep(random.uniform(1, 5))
        groups = await sv.get_enable_groups()
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
        msgs = await dyn.get_msg(False)
        for gid in gids:
            await asyncio.sleep(random.uniform(2, 5))
            bot = groups[gid][0]
            db.update(time=dyn.timestamp, name=dyn.nickname).where(
                db.uid == uid, db.group == gid
            ).execute()
            try:
                if msgs:
                    m = msgs[0]
                    await bot.send_group_msg(group_id=gid, message=m)
                    await asyncio.sleep(random.uniform(1, 3))
                    await send_group_segments(bot, gid, msgs[1:])
                else:
                    await bot.send(gid, "获取微博失败")
            except Exception as e:
                sv.logger.error(f"发送 weibo post 失败: {e}")
        weibo_queue.remove_id(dyn.id)


async def weibo_dispatcher():
    sem = asyncio.Semaphore(5)
    while True:
        dyn = weibo_queue.get()
        if not dyn:
            await asyncio.sleep(0.5)
            continue
        asyncio.create_task(handle_weibo_dyn(dyn, sem))


@on_startup
async def start_weibo_dispatcher():
    # 初始化 UID 管理器
    await uid_manager.init_from_db()
    asyncio.create_task(weibo_dispatcher())
