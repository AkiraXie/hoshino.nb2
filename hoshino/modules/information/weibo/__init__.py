# Thanks to https://github.com/MountainDash/nonebot-bison

import asyncio
from dataclasses import replace
from datetime import datetime
import time
from hoshino import Bot, Event, on_startup, Message, SUPERUSER
from hoshino.schedule import scheduled_job
from hoshino.util import (
    send_group_segments,
    send_segments,
    send_to_superuser,
    random_image_or_video_by_path,
)
from .utils import (
    get_weibo_list,
    sv,
    WeiboDB as db,
    WeiboPost,
    get_weibo_new,
    Session,
    parse_mapp_weibo,
    parse_weibo_with_id,
    weibo_img_dir,
    weibo_video_dir,
)
from hoshino.event import GroupReactionEvent
from nonebot.typing import T_State
from nonebot.compat import type_validate_python
from ..utils import PostQueue, UIDManager
from sqlalchemy import select

import re
import random

weibo_queue = PostQueue[WeiboPost]()
uid_manager = UIDManager()

WEIBO_FETCH_BATCH_SIZE = 8
WEIBO_FETCH_CONCURRENCY = 4
WEIBO_COLD_UID_THRESHOLD = 24 * 60 * 60
weibo_fetch_lock = asyncio.Lock()




weibo_regexs = {
    "weibo": re.compile(r"(http:|https:)\/\/weibo\.com\/(\d+)\/(\w+)"),
    "mweibo": re.compile(r"(http:|https:)\/\/m\.weibo\.cn\/(detail|status)\/(\w+)"),
    "mappweibo": re.compile(r"(http:|https:)\/\/mapp\.api\.weibo\.cn\/fx\/(\w+)\.html"),
}


async def reaction_weibo_img_rule(
    bot: Bot,
    event: GroupReactionEvent,
    state: T_State,
) -> bool:
    if event.code != "282" and event.code != "319":
        return False
    msg_id = event.message_id
    msg = await bot.get_msg(message_id=msg_id)
    sender = msg.get("sender", {}).get("user_id")
    sender = str(sender)
    if sender != bot.self_id and sender not in bot.config.superusers:
        return False
    msg = msg.get("message")
    if msg:
        msg = type_validate_python(Message, msg)
        text = msg.extract_plain_text()
        url = text.strip()
        for name, regex in weibo_regexs.items():
            matched = regex.search(url)
            if matched:
                state["__weibo_name"] = name
                state["__weibo_url"] = matched.group(0)
                state["__weibo_matched"] = matched
                state["__weibo_included_video"] = event.code == "319"
                return True
    return False


svimg_notice = sv.on_notice(
    rule=reaction_weibo_img_rule,
    permission=SUPERUSER,
    priority=5,
    block=True,
)


@svimg_notice.handle()
async def handle_weibo_img_reaction(state: T_State):
    if not (name := state.get("__weibo_name")):
        return
    if not (matched := state.get("__weibo_matched")):
        return
    if not (url := state.get("__weibo_url")):
        return
    included_video = state.get("__weibo_included_video", False)
    name = name.lower()
    post = None
    match name:
        case "weibo":
            _, _, bid = matched.groups()
            post = await parse_weibo_with_id(bid)
        case "mweibo":
            _, _, bid = matched.groups()
            post = await parse_weibo_with_id(bid)
        case "mappweibo":
            post = await parse_mapp_weibo(url)
    if not post:
        await send_to_superuser(f"无法解析微博链接: {url}")
        return
    res = await post.download_images()
    if included_video:
        video_res = await post.download_videos()
        if video_res:
            res.extend(video_res)
    if not res:
        await send_to_superuser("获取微博图片失败")
        return
    res = [i.name for i in res]
    await send_to_superuser(f"获取微博图片成功:\n {'\n'.join(res)}")
    return


@sv.on_command(
    "微博随图",
    aliases=("wbimg", "wim"),
    only_group=False,
    only_to_me=True,
    permission=SUPERUSER,
    priority=5,
)
async def weibo_random_image(event: Event):
    path = weibo_img_dir
    num = 12
    text = event.get_plaintext().strip()
    texts = text.split(maxsplit=1)
    keyword = None
    if len(texts) == 2:
        keyword, num_str = texts
        if num_str.isdigit():
            num = int(num_str)
        else:
            keyword = keyword + num_str
    elif len(texts) == 1:
        keyword = texts[0]
        if keyword.isdigit():
            num = int(keyword)
    seed = time.time() + event.message_id
    imgs = random_image_or_video_by_path(
        path, num=num, seed=seed, video=False, keyword=keyword
    )
    await send_segments(imgs)


@sv.on_command(
    "微博随影",
    aliases=("wbvid", "wvi"),
    only_to_me=True,
    only_group=False,
    permission=SUPERUSER,
    priority=5,
)
async def weibo_random_video(event: Event):
    path = weibo_video_dir
    num = 2
    text = event.get_plaintext().strip()
    texts = text.split(maxsplit=1)
    keyword = None
    if len(texts) == 2:
        keyword, num_str = texts
        if num_str.isdigit():
            num = int(num_str)
        else:
            keyword = keyword + num_str
    elif len(texts) == 1:
        keyword = texts[0]
        if keyword.isdigit():
            num = int(keyword)
    seed = time.time() + event.message_id
    imgs = random_image_or_video_by_path(
        path, num=num, seed=seed, video=True, keyword=keyword
    )
    await send_segments(imgs)


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
        post = await get_weibo_new(uid, ts=0)
        if not post:
            await bot.send(event, f"无法获取微博用户信息，UID: {uid}")
            return
    except Exception as e:
        sv.logger.exception(e)
        await bot.send(event, f"无法获取微博用户信息，UID: {uid}")
        return
    kw = "-_-".join(keywords) if keywords else ""
    ts = time.time()
    with Session() as session:
        stmt = select(db).where(db.group == gid, db.uid == uid)
        obj = session.execute(stmt).scalar_one_or_none()
        if obj:
            obj.name = post.nickname
            obj.time = ts
            obj.keyword = kw
        else:
            obj = db(group=gid, uid=uid, name=post.nickname, time=ts, keyword=kw)
            session.add(obj)
        session.commit()
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
    uids = event.get_plaintext().strip()
    uids = uids.split()
    for uid in uids:
        with Session() as session:
            await asyncio.sleep(0.3)
            if uid.isdecimal():
                stmt = select(db).where(db.group == gid, db.uid == uid)
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
                            target_uid,
                            lambda u: bool(
                                session.execute(
                                    select(db).where(db.uid == u)
                                ).scalar_one_or_none()
                            ),
                        )
                else:
                    num = 0
            if num:
                await bot.send(event, f"{uid} 删除微博订阅成功")
            else:
                await bot.send(event, f"{uid} 删除微博订阅失败")


@sv.on_command("微博订阅", aliases=("微博订阅列表", "lookweibo", "lswb", "listweibo"))
async def list_subscriptions(bot: Bot, event: Event):
    gid = event.group_id
    with Session() as session:
        stmt = select(db).where(db.group == gid)
        rows = session.execute(stmt).scalars().all()
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
    with Session() as session:
        if arg.isdecimal():
            stmt = select(db).where(db.group == gid, db.uid == arg)
            rows = session.execute(stmt).scalars().all()
        else:
            stmt = select(db).where(db.group == gid, db.name == arg)
            rows = session.execute(stmt).scalars().all()
    if not rows:
        await bot.send(event, f"没有订阅{arg}微博")
    else:
        uid = rows[0].uid
        keywords = rows[0].keyword
        if keywords:
            keywords = keywords.split("-_-")
        else:
            keywords = []
        post = await get_weibo_new(uid, 0)
        if not post:
            await bot.send(event, f"没有获取到{arg}微博")
            return
        msgs = await post.get_message()
        await send_segments(msgs)

@sv.on_command("查库微博", aliases=("wbquery", "微博查库"), permission=SUPERUSER,only_group=False,only_to_me=True)
async def query_weibo_user(bot: Bot, event: Event):
    arg = event.get_plaintext().strip()
    with Session() as session:
        if arg.isdecimal():
            stmt = select(db).where(db.uid == arg)
            rows = session.execute(stmt).scalars().all()
        else:
            stmt = select(db).where(db.name == arg)
            rows = session.execute(stmt).scalars().all()
    if not rows:
        await bot.send(event, f"没有查到微博用户 {arg}")
        return
    msg = "微博用户信息:\n"
    for row in rows:
        msg += (
            f"UID: {row.uid}, 昵称: {row.name}, 关键词: {row.keyword or '无'}, "
            f"上次更新时间: {datetime.fromtimestamp(row.time).strftime('%Y-%m-%d %H:%M:%S')}\n"
        )
        break
    await bot.send(event, msg)

@scheduled_job("interval", seconds=15, jitter=3, id="获取微博更新")
async def fetch_weibo_updates():
    if weibo_fetch_lock.locked():
        return

    uid_count = uid_manager.get_count()
    if uid_count == 0:
        return

    batch_size = min(uid_count, WEIBO_FETCH_BATCH_SIZE)
    uids: list[str] = []
    for _ in range(batch_size):
        uid_str = await uid_manager.get_next_uid()
        if not uid_str:
            break
        uids.append(uid_str)

    if not uids:
        return

    sem = asyncio.Semaphore(WEIBO_FETCH_CONCURRENCY)

    async def _worker(uid_str: str):
        async with sem:
            success = await _fetch_weibo_updates_for_uid(uid_str)
            await uid_manager.finish_processing(uid_str, success)

    async with weibo_fetch_lock:
        await asyncio.gather(*(_worker(uid_str) for uid_str in uids))



def match_keywords(post: WeiboPost, keywords: list[str]) -> bool:
    if not keywords:
        return True

    if any(keyword in post.content for keyword in keywords):
            return True
    if post.repost and any(keyword in post.repost.content for keyword in keywords):
            return True
    return False

def clone_post_for_group(post: WeiboPost, group_id: int | str) -> WeiboPost:
    repost = None
    if post.repost:
        repost = clone_post_for_group(post.repost, group_id)
    return replace(post, repost=repost, group_id=str(group_id))

async def _fetch_weibo_updates_for_uid(uid_str: str) -> bool:

    try:
        with Session() as session:
            stmt = select(db).where(db.uid == uid_str)
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
            return True

        latest_known_ts = max(row.time for row in rows)
        now_ts = time.time()

        if latest_known_ts > 0 and now_ts - latest_known_ts > WEIBO_COLD_UID_THRESHOLD:
            await uid_manager.mark_cold(uid_str)
        
        min_ts = max(now_ts - WEIBO_COLD_UID_THRESHOLD, latest_known_ts)
        posts = await get_weibo_list(uid_str, min_ts)
        if not posts:
            return True

        await uid_manager.unmark_cold(uid_str)

        matched_posts: list[WeiboPost] = []
        for row in rows:
            if row.keyword:
                row_keywords = [kw for kw in row.keyword.split("-_-") if kw]
            else:
                row_keywords = []

            for post in posts:
                if post.timestamp <= row.time:
                    continue
                if not match_keywords(post, row_keywords):
                    continue
                matched_posts.append(clone_post_for_group(post, row.group))

        if not matched_posts:
            return True

        for post in matched_posts:
            b = weibo_queue.put(post)
            if b:
                sv.logger.info(
                    f"获取到微博更新: {post.uid} {post.nickname} {post.group_id} {post.timestamp} {post.url}"
                )

        latest_ts = max(post.timestamp for post in posts)
        with Session() as session:
            stmt = select(db).where(db.uid == uid_str)
            db_rows = session.execute(stmt).scalars().all()
            for row in db_rows:
                row.time = latest_ts
                row.name = posts[0].nickname
            session.commit()
        return True

    except Exception as e:
        sv.logger.error(f"获取微博更新失败 UID {uid_str}: {e}")
        return False


async def handle_weibo_dyn(dyn: WeiboPost, sem: asyncio.Semaphore):
    async with sem:
        sv.logger.info(
            f"推送微博更新: {dyn.uid} {dyn.nickname} {dyn.group_id} {dyn.timestamp} {dyn.url}"
        )
        if not dyn.group_id:
            weibo_queue.remove(dyn)
            await asyncio.sleep(0.5)
            return

        gid = int(dyn.group_id)
        await asyncio.sleep(random.uniform(0, 1))
        groups = await sv.get_enable_groups()
        if gid not in groups:
            weibo_queue.remove(dyn)
            await asyncio.sleep(0.5)
            return

        msgs = await dyn.get_message(True)
        bot = groups[gid][0]
        try:
            if msgs:
                m = msgs[0]
                await bot.send_group_msg(group_id=gid, message=m)
                await asyncio.sleep(random.uniform(0, 0.5))
                await send_group_segments(bot, gid, msgs[1:])
        except Exception as e:
            sv.logger.error(f"发送 weibo post 失败: {e}")
        weibo_queue.remove(dyn)
        await asyncio.sleep(1)


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
    with Session() as session:
        rows = session.execute(select(db.uid, db.time)).all()

    uid_latest_time: dict[str, float] = {}
    for uid, ts in rows:
        uid_str = str(uid)
        uid_latest_time[uid_str] = max(uid_latest_time.get(uid_str, 0.0), float(ts or 0.0))

    uids = list(uid_latest_time)
    random.shuffle(uids)
    await uid_manager.init(uids)

    now_ts = time.time()
    for uid, latest_ts in uid_latest_time.items():
        if latest_ts > 0 and now_ts - latest_ts > WEIBO_COLD_UID_THRESHOLD:
            await uid_manager.mark_cold(uid)

    asyncio.create_task(weibo_dispatcher())
