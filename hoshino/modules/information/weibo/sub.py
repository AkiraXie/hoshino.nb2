import asyncio

from hoshino.core.hooks import on_post_startup, on_shutdown, on_startup, spawn
from hoshino.core.schedule import scheduled_job

from ..utils import UIDManager
from .db import list_uid_time_pairs
from .internal.outbox import WeiboOutboxStore
from .internal.sub_runtime import (
    WEIBO_COLD_UID_THRESHOLD,
    WeiboDispatchRuntime,
)
from .sv import sv

outbox = WeiboOutboxStore()
uid_manager = UIDManager()
runtime = WeiboDispatchRuntime(
    outbox=outbox,
    uid_manager=uid_manager,
    cold_uid_threshold=WEIBO_COLD_UID_THRESHOLD,
)

# 后台任务引用：微博推送 worker 循环，shutdown 时取消
_dispatch_worker_task: asyncio.Task | None = None


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
    global _dispatch_worker_task
    _dispatch_worker_task = spawn(_weibo_dispatch_worker())


@on_shutdown
async def stop_weibo_dispatch_worker():
    if _dispatch_worker_task:
        _dispatch_worker_task.cancel()


__all__ = ["uid_manager"]
