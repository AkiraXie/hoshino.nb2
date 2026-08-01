import asyncio
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI


def build_lifespan(
    build_index: Callable[[], None],
    interval: int,
    on_startup: Callable[[], Awaitable[None]] | None = None,
    on_shutdown: Callable[[], Awaitable[None]] | None = None,
):
    """构造 lifespan：启动时构建索引并周期刷新，可选启停钩子。"""

    async def _refresh_loop() -> None:
        while True:
            await asyncio.sleep(interval)
            await asyncio.to_thread(build_index)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        await asyncio.to_thread(build_index)
        if on_startup is not None:
            await on_startup()
        task = asyncio.create_task(_refresh_loop())
        try:
            yield
        finally:
            task.cancel()
            if on_shutdown is not None:
                await on_shutdown()

    return lifespan
