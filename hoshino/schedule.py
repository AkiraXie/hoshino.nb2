from functools import wraps
from nonebot_plugin_apscheduler import scheduler
from loguru import logger
from apscheduler import job
from .typing import Callable, Any, Awaitable


def wrapper(func: Callable[[], Any], id: str) -> Callable[[], Awaitable[Any]]:
    @wraps(func)
    async def _wrapper() -> Awaitable[Any]:
        try:
            logger.opt(colors=True).info(
                f'<ly>Scheduled job <c>{id}</c> started.</ly>')
            res = await func()
            logger.opt(colors=True).info(
                f'<ly>Scheduled job <c>{id}</c> completed.</ly>')
            return res
        except Exception as e:
            logger.opt(colors=True, exception=e).error(
                f'<r><bg #f8bbd0>Scheduled job <c>{id}</c> failed.</bg #f8bbd0></r>')
    return _wrapper


def scheduled_job(trigger: str, **kwargs):
    def deco(func: Callable[[], Any]) -> Callable[[], Awaitable[Any]]:
        id = kwargs.get('id', func.__name__)
        kwargs['id'] = id
        return scheduler.scheduled_job(trigger, **kwargs)(wrapper(func, id))
    return deco


def add_job(func: Callable[[], Any], trigger: str, **kwargs)->job.Job:
    id = kwargs.get('id', func.__name__)
    kwargs['id'] = id
    return scheduler.add_job(wrapper(func, id), trigger, **kwargs)
