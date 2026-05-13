import asyncio

from hoshino import on_startup
from hoshino.util import save_cookies, send_to_superuser, sucmd

from .pw import get_weibo_cookies_from_local
from .internal.request_runtime import (
    WeiboRequestError,
    get_weibo_list,
    get_weibo_new,
    get_weibocookies,
    missing_weibo_target_worker,
    parse_mapp_weibo,
    parse_weibo_with_id,
)
from .sv import sv


wbck = sucmd("weibocookies", aliases={"wbck", "rfwb"})


@wbck.handle()
async def get_weibocookies_cmd():
    try:
        await initialize_weibo_cookies()
        ck = await get_weibocookies()
        if ck:
            await send_to_superuser("Weibo cookies refreshed successfully")
    except Exception:
        sv.logger.error("Failed to initialize or get Weibo cookies")


@on_startup
async def initialize_weibo_cookies():
    ck = await get_weibo_cookies_from_local()
    await save_cookies("weibo", ck)
@on_startup
async def start_missing_weibo_target_worker() -> None:
    asyncio.create_task(missing_weibo_target_worker())


__all__ = [
    "WeiboRequestError",
    "get_weibo_list",
    "get_weibo_new",
    "get_weibocookies",
    "initialize_weibo_cookies",
    "parse_mapp_weibo",
    "parse_weibo_with_id",
    "wbck",
]
