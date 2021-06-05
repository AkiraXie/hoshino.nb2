'''
Author: AkiraXie
LastEditTime: 2021-06-05 12:16:03
LastEditors: AkiraXie
GitHub: https://github.com/AkiraXie
'''
from functools import wraps
from nonebot_plugin_apscheduler import scheduler
from loguru import logger
from apscheduler import job
from .typing import Callable, Any, Awaitable, List, Dict, Optional


def wrapper(func: Callable[[], Any], id: str, args: Optional[List] = None, kwargs: Optional[Dict] = None) -> Callable[[], Awaitable[Any]]:
    @wraps(func)
    async def _wrapper() -> Awaitable[Any]:
        try:
            logger.opt(colors=True).info(
                f'<ly>Scheduled job <c>{id}</c> started.</ly>')
            if kwargs is None and args is not None:
                res = await func(*args)
            elif kwargs is not None and args is None:
                res = await func(**kwargs)
            elif  args is None and kwargs is None:
                res = await func()
            else:
                res = await func(*args, **kwargs)
            logger.opt(colors=True).info(
                f'<ly>Scheduled job <c>{id}</c> completed.</ly>')
            return res
        except Exception as e:
            logger.opt(colors=True, exception=e).error(
                f'<r><bg #f8bbd0>Scheduled job <c>{id}</c> failed.</bg #f8bbd0></r>')
    return _wrapper


def scheduled_job(trigger: str, args: Optional[List] = None, kwargs: Optional[Dict] = None, **triger_kwargs):
    def deco(func: Callable[[], Any]) -> Callable[[], Awaitable[Any]]:
        id = triger_kwargs.get('id', func.__name__)
        triger_kwargs['id'] = id
        return scheduler.scheduled_job(trigger, **triger_kwargs)(wrapper(func, id, args, kwargs))
    return deco


def add_job(func: Callable[[], Any], trigger: str, args: Optional[List] = None, kwargs: Optional[Dict] = None, **triger_kwargs) -> job.Job:
    id = triger_kwargs.get('id', func.__name__)
    triger_kwargs['id'] = id
    return scheduler.add_job(wrapper(func, id, args, kwargs), trigger, **triger_kwargs)
