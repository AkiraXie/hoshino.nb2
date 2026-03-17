import asyncio
from dataclasses import replace
import random
import time

from hoshino import on_startup
from hoshino.schedule import scheduled_job

from .db import (
    get_group_config,
    list_subscriptions_by_uid,
    list_uid_time_pairs,
    uid_has_any_subscription,
    update_subscriptions_for_uid,
)
from .utils import WeiboPost, get_weibo_list, sv
from ..utils import PostQueue, UIDManager


weibo_queue = PostQueue[WeiboPost]()
uid_manager = UIDManager()

WEIBO_FETCH_BATCH_SIZE = 4
WEIBO_FETCH_CONCURRENCY = 4
WEIBO_COLD_UID_THRESHOLD = 24 * 60 * 60
WEIBO_DISPATCH_WORKER_COUNT = 8
weibo_fetch_lock = asyncio.Lock()
weibo_dispatch_state_lock = asyncio.Lock()
active_weibo_dispatches = 0


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
        rows = list_subscriptions_by_uid(uid_str)
        if not rows:
            await uid_manager.remove_uid(
                uid_str,
                lambda u: uid_has_any_subscription(u),
            )
            return True

        latest_known_ts = max(row.time for row in rows)
        now_ts = time.time()

        if (
            latest_known_ts > 0
            and now_ts - latest_known_ts > 2 * WEIBO_COLD_UID_THRESHOLD
        ):
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
            queued = weibo_queue.put(post)
            if queued:
                sv.logger.info(
                    f"获取到微博更新: {post.uid} {post.nickname} {post.group_id} {post.timestamp} {post.url}"
                )

        latest_ts = max(post.timestamp for post in posts)
        update_subscriptions_for_uid(uid_str, latest_ts, posts[0].nickname)
        return True

    except Exception as e:
        sv.logger.error(f"获取微博更新失败 UID {uid_str}: {e}")
        return False


async def handle_weibo_dyn(dyn: WeiboPost):
    global active_weibo_dispatches
    async with weibo_dispatch_state_lock:
        active_weibo_dispatches += 1
        current_dispatches = active_weibo_dispatches

    removed = False
    sleep_delay = 1.0
    try:
        sv.logger.info(
            f"推送微博更新: {dyn.uid} {dyn.nickname} {dyn.group_id} {dyn.timestamp} {dyn.url}, active={current_dispatches}"
        )
        gid = dyn.gid
        if gid is None:
            weibo_queue.remove(dyn)
            removed = True
            sleep_delay = 0.5
            return

        await asyncio.sleep(random.uniform(0.1, 1))
        groups = await sv.get_enable_groups()
        if gid not in groups:
            weibo_queue.remove(dyn)
            removed = True
            sleep_delay = 0.5
            return

        busy = current_dispatches > WEIBO_DISPATCH_WORKER_COUNT / 2
        sv.logger.info(
            "微博推送准备发送: "
            f"group={gid} uid={dyn.uid} post={dyn.id} active={current_dispatches} busy={busy} "
        )
        group_config = get_group_config(gid)
        bot = groups[gid][0]
        await dyn.build_and_send_message(group_config, busy, bot, gid)

    except Exception as e:
        sv.logger.error(f"发送 weibo post 失败: {e}")
    finally:
        if not removed:
            weibo_queue.remove(dyn)
        await asyncio.sleep(sleep_delay)
        async with weibo_dispatch_state_lock:
            active_weibo_dispatches = max(0, active_weibo_dispatches - 1)
            sv.logger.info(
                f"微博推送完成: uid={dyn.uid} post={dyn.id} active={active_weibo_dispatches}"
            )


async def weibo_dispatch_worker(worker_id: int):
    while True:
        dyn = weibo_queue.get()
        if not dyn:
            await asyncio.sleep(0.5)
            continue
        try:
            await handle_weibo_dyn(dyn)
        except Exception as e:
            sv.logger.error(f"微博推送 worker {worker_id} 处理失败: {e}")
            weibo_queue.remove(dyn)
            await asyncio.sleep(1)


@on_startup
async def start_weibo_dispatcher():
    rows = list_uid_time_pairs()

    uid_latest_time: dict[str, float] = {}
    for uid, ts in rows:
        uid_str = str(uid)
        uid_latest_time[uid_str] = max(
            uid_latest_time.get(uid_str, 0.0), float(ts or 0.0)
        )

    uids = list(uid_latest_time)
    random.shuffle(uids)
    await uid_manager.init(uids)

    now_ts = time.time()
    for uid, latest_ts in uid_latest_time.items():
        if latest_ts > 0 and now_ts - latest_ts > WEIBO_COLD_UID_THRESHOLD:
            await uid_manager.mark_cold(uid)

    for worker_id in range(WEIBO_DISPATCH_WORKER_COUNT):
        asyncio.create_task(weibo_dispatch_worker(worker_id))


__all__ = ["uid_manager"]
