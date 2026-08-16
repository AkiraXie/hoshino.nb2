import asyncio
import logging
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI

logger = logging.getLogger(__name__)


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
            try:
                await asyncio.to_thread(build_index)
            except Exception:
                # 单次刷新失败不能杀死后台循环，否则索引将永久停止更新。
                logger.exception("periodic index refresh failed")

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
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception:
                logger.exception("index refresh loop terminated with an error")
            if on_shutdown is not None:
                await on_shutdown()

    return lifespan
