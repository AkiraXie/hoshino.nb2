# Thanks to https://github.com/MountainDash/nonebot-bison

import asyncio
from datetime import datetime
from typing import List
from hoshino import Bot, Event, on_startup
from hoshino.schedule import scheduled_job
from hoshino.util import send_group_segments, send_segments
from .utils import (
    get_sub_list,
    sv,
    WeiboDB as db,
    WeiboPost,
    get_sub_new,
)
from ..utils import PostQueue, UIDManager

import re
import random

weibo_queue = PostQueue()
uid_manager = UIDManager("weibo")


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
                return
        post = await get_sub_new(uid, 0, keywords=keywords)
        if not post:
            post = await get_sub_new(uid, 0)
    except Exception as e:
        sv.logger.exception(e)
        await bot.send(event, f"无法获取微博用户信息，UID: {uid}")
        return
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
            await uid_manager.remove_uid(
                uid, lambda u: bool(db.select().where(db.uid == u).execute())
            )
    else:
        # 先获取 UID 再删除
        rows = db.select().where(db.group == gid, db.name == uid).execute()
        if rows:
            target_uid = rows[0].uid
            deleted_rows = db.delete().where(db.group == gid, db.name == uid).execute()
            if deleted_rows:
                await uid_manager.remove_uid(
                    target_uid, lambda u: bool(db.select().where(db.uid == u).execute())
                )
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
        if not post:
            await bot.send(event, f"没有获取到{arg}微博")
            return
        msgs = await post.get_message()
        await send_segments(msgs)


@scheduled_job("interval", seconds=1, jitter=0.2, id="获取微博更新")
async def fetch_weibo_updates():
    uid_count = uid_manager.get_count()
    if uid_count == 0:
        return

    uid_str = await uid_manager.get_next_uid()
    if not uid_str:
        return

    success = False
    try:
        rows: List[db] = db.select().where(db.uid == uid_str).execute()
        if not rows:
            await uid_manager.remove_uid(
                uid_str, lambda u: bool(db.select().where(db.uid == u).execute())
            )
            return

        time_rows = sorted(rows, key=lambda x: x.time, reverse=True)
        min_ts = time_rows[0].time
        kw = time_rows[0].keyword
        if kw:
            kw = kw.split("-_-")
        else:
            kw = []

        posts = await get_sub_list(uid_str, min_ts, kw)
        if not posts:
            success = True
            return

        max_timestamp = max(post.timestamp for post in posts)
        for post in posts:
            post.timestamp = max_timestamp
            b = weibo_queue.put(post)
            if b:
                sv.logger.info(
                    f"获取到微博更新: {post.uid} {post.nickname} {post.timestamp} {post.url}"
                )
        success = True

    except Exception as e:
        sv.logger.error(f"获取微博更新失败 UID {uid_str}: {e}")
        success = False
    finally:
        await uid_manager.finish_processing(uid_str, success)


async def handle_weibo_dyn(dyn: WeiboPost, sem: asyncio.Semaphore):
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

        # 直接使用 Post 对象的 get_message 方法
        msgs = await dyn.get_message(False)
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
    uids = [str(row.uid) for row in db.select(db.uid).distinct()]
    await uid_manager.init(uids)
    asyncio.create_task(weibo_dispatcher())
