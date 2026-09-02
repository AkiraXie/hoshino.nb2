import sys
from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Any

import nonebot
from apscheduler import job
from loguru import logger

# schedule 仅在插件加载后使用；未加载时 require，已导入则跳过。
from nonebot.plugin import get_plugin

if (
    get_plugin("nonebot_plugin_apscheduler") is None
    and "nonebot_plugin_apscheduler" not in sys.modules
):
    nonebot.require("nonebot_plugin_apscheduler")
from nonebot_plugin_apscheduler import scheduler as _scheduler


def _get_scheduler():
    return _scheduler


def wrapper(
    func: Callable[[], Any],
    id: str,
    args: list | None = None,
    kwargs: dict[str, Any] | None = None,
):
    @wraps(func)
    async def _wrapper():
        try:
            logger.opt(colors=True).debug(f"<ly>Scheduled job <c>{id}</c> started.</ly>")
            if kwargs is None and args is not None:
                res = await func(*args)
            elif kwargs is not None and args is None:
                res = await func(**kwargs)
            elif args is None and kwargs is None:
                res = await func()
            else:
                res = await func(*args, **kwargs)
            logger.opt(colors=True).debug(f"<ly>Scheduled job <c>{id}</c> completed.</ly>")
            return res
        except Exception as e:
            logger.opt(colors=True, exception=e).error(
                f"<r><bg #f8bbd0>Scheduled job <c>{id}</c> failed.</bg #f8bbd0></r>"
            )

    return _wrapper


def scheduled_job(
    trigger: str,
    args: list | None = None,
    kwargs: dict[str, Any] | None = None,
    **triger_kwargs,
):
    def deco(func: Callable[[], Any]) -> Callable[[], Awaitable[Any]]:
        triger_kwargs.setdefault("timezone", "Asia/Shanghai")
        triger_kwargs.setdefault("misfire_grace_time", 60)
        triger_kwargs.setdefault("coalesce", True)
        id = triger_kwargs.get("id", func.__name__)
        triger_kwargs["id"] = id
        sched = _get_scheduler()
        return sched.scheduled_job(trigger, **triger_kwargs)(wrapper(func, id, args, kwargs))

    return deco


def add_job(
    func: Callable[[], Any],
    trigger: str,
    args: list | None = None,
    kwargs: dict[str, Any] | None = None,
    **triger_kwargs,
) -> job.Job:
    triger_kwargs.setdefault("timezone", "Asia/Shanghai")
    triger_kwargs.setdefault("misfire_grace_time", 60)
    triger_kwargs.setdefault("coalesce", True)
    id = triger_kwargs.get("id", func.__name__)
    triger_kwargs["id"] = id
    sched = _get_scheduler()
    return sched.add_job(wrapper(func, id, args, kwargs), trigger, **triger_kwargs)
