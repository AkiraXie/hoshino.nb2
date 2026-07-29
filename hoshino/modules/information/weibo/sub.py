import asyncio

from hoshino.core.hooks import on_post_startup, on_startup
from hoshino.core.schedule import scheduled_job

from .db import list_uid_time_pairs
from .internal.outbox import WeiboOutboxStore
from .internal.sub_runtime import (
    WEIBO_COLD_UID_THRESHOLD,
    WeiboDispatchRuntime,
)
from .sv import sv
from ..utils import UIDManager


outbox = WeiboOutboxStore()
uid_manager = UIDManager()
runtime = WeiboDispatchRuntime(
    outbox=outbox,
    uid_manager=uid_manager,
    cold_uid_threshold=WEIBO_COLD_UID_THRESHOLD,
)


@scheduled_job("interval", seconds=3, jitter=0.2, id="获取微博更新")
async def fetch_weibo_updates():
    await runtime.fetch_next_update()


async def _weibo_dispatch_worker():
    while True:
        try:
            sent = await runtime.dispatch_pending()
        except Exception:
            sv.logger.exception("微博推送 worker 异常")
            sent = 0
        await asyncio.sleep(0 if sent else 0.5)


@on_startup
async def start_weibo_dispatcher():
    await runtime.bootstrap(list_uid_time_pairs())


@on_post_startup
async def start_weibo_dispatch_worker():
    asyncio.create_task(_weibo_dispatch_worker())


__all__ = ["uid_manager"]
