from hoshino import on_startup
from hoshino.schedule import scheduled_job

from .db import list_uid_time_pairs
from .internal.post_runtime import WeiboDispatchTask
from .internal.sub_runtime import (
    WEIBO_COLD_UID_THRESHOLD,
    WEIBO_DISPATCH_WORKER_COUNT,
    WeiboDispatchRuntime,
)
from ..utils import PostQueue, UIDManager


weibo_queue = PostQueue[WeiboDispatchTask]()
uid_manager = UIDManager()
runtime = WeiboDispatchRuntime(
    weibo_queue=weibo_queue,
    uid_manager=uid_manager,
    dispatch_worker_count=WEIBO_DISPATCH_WORKER_COUNT,
    cold_uid_threshold=WEIBO_COLD_UID_THRESHOLD,
)


@scheduled_job("interval", seconds=3, jitter=0.2, id="获取微博更新")
async def fetch_weibo_updates():
    await runtime.fetch_next_update()


@on_startup
async def start_weibo_dispatcher():
    await runtime.bootstrap(list_uid_time_pairs())


__all__ = ["uid_manager"]
