"""延迟生命周期 hook 注册表。

bootstrap() 前收集回调，bootstrap() 时统一下发到真实 driver。
使得 ``from hoshino.hooks import on_startup`` 在 nonebot.init() 前也能正常使用。

``import nonebot`` / ``nonebot.message`` 在 init 前是安全的；不安全的是在 init
前调用 ``get_driver()``。因此本模块顶层 import nonebot，仅在 ``_replayed`` 后
才 ``get_driver()``。
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from typing import Any

import nonebot
from loguru import logger
from nonebot.message import event_preprocessor as _event_preprocessor
from nonebot.message import run_preprocessor as _run_preprocessor

# 持有后台任务强引用，防止 task 被 GC；done 回调中移除并记录异常。
_background_tasks: set[asyncio.Task] = set()


def _on_task_done(task: asyncio.Task) -> None:
    _background_tasks.discard(task)
    if task.cancelled():
        return
    if exc := task.exception():
        logger.error(f"后台任务异常: {exc}")


def spawn(coro: Coroutine[Any, Any, Any]) -> asyncio.Task:
    """启动一个后台任务并持有其引用，避免被 GC 回收、异常无人接收。

    用法：``spawn(some_coro())``；返回值仅在需要取消任务时使用。
    """
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_on_task_done)
    return task


class _Registry:
    def __init__(self) -> None:
        self._startup: list[Callable] = []
        self._serial_startup: list[Callable] = []
        self._post_startup: list[Callable] = []
        self._shutdown: list[Callable] = []
        self._bot_connect: list[Callable] = []
        self._bot_disconnect: list[Callable] = []
        self._preprocessors: list[Callable] = []
        self._event_preprocessors: list[Callable] = []
        self._replayed = False

    def on_startup(self, func: Callable) -> Callable:
        if self._replayed:
            return nonebot.get_driver().on_startup(func)
        self._startup.append(func)
        return func

    def on_serial_startup(self, func: Callable) -> Callable:
        """串行 startup 回调，按注册顺序依次执行，阻塞 server 启动。"""
        if self._replayed:

            async def _wrapper():
                await func()

            return nonebot.get_driver().on_startup(_wrapper)
        self._serial_startup.append(func)
        return func

    def on_post_startup(self, func: Callable) -> Callable:
        """Server 启动后执行的后台任务，不阻塞启动。"""
        if self._replayed:

            async def _wrapper():
                spawn(func())

            return nonebot.get_driver().on_startup(_wrapper)
        self._post_startup.append(func)
        return func

    def on_shutdown(self, func: Callable) -> Callable:
        if self._replayed:
            return nonebot.get_driver().on_shutdown(func)
        self._shutdown.append(func)
        return func

    def on_bot_connect(self, func: Callable) -> Callable:
        if self._replayed:
            return nonebot.get_driver().on_bot_connect(func)
        self._bot_connect.append(func)
        return func

    def on_bot_disconnect(self, func: Callable) -> Callable:
        if self._replayed:
            return nonebot.get_driver().on_bot_disconnect(func)
        self._bot_disconnect.append(func)
        return func

    def run_preprocessor(self, func: Callable) -> Callable:
        if self._replayed:
            return _run_preprocessor(func)
        self._preprocessors.append(func)
        return func

    def event_preprocessor(self, func: Callable) -> Callable:
        if self._replayed:
            return _event_preprocessor(func)
        self._event_preprocessors.append(func)
        return func

    async def _run_serial_and_post(self) -> None:
        for fn in self._serial_startup:
            await fn()
        if self._post_startup:

            async def _run_post():
                for fn in self._post_startup:
                    await fn()

            spawn(_run_post())

    def replay(self, driver) -> None:
        if self._serial_startup or self._post_startup:
            driver.on_startup(self._run_serial_and_post)
        for fn in self._startup:
            driver.on_startup(fn)
        for fn in self._shutdown:
            driver.on_shutdown(fn)
        for fn in self._bot_connect:
            driver.on_bot_connect(fn)
        for fn in self._bot_disconnect:
            driver.on_bot_disconnect(fn)
        for fn in self._preprocessors:
            _run_preprocessor(fn)
        for fn in self._event_preprocessors:
            _event_preprocessor(fn)

        self._replayed = True
        self._startup.clear()
        self._serial_startup.clear()
        self._post_startup.clear()
        self._shutdown.clear()
        self._bot_connect.clear()
        self._bot_disconnect.clear()
        self._preprocessors.clear()
        self._event_preprocessors.clear()


_reg = _Registry()

on_startup = _reg.on_startup
on_serial_startup = _reg.on_serial_startup
on_post_startup = _reg.on_post_startup
on_shutdown = _reg.on_shutdown
on_bot_connect = _reg.on_bot_connect
on_bot_disconnect = _reg.on_bot_disconnect
run_preprocessor = _reg.run_preprocessor
event_preprocessor = _reg.event_preprocessor  # 兼容别名，同 run_preprocessor


def replay(driver) -> None:
    _reg.replay(driver)
