import asyncio

from nonebot.adapters import Bot

from hoshino.core.hooks import on_post_startup
from hoshino.platform import send_to_superuser
from hoshino.util.command import sucmd
from hoshino.util.cookies import save_cookies

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
async def get_weibocookies_cmd(bot: Bot):
    try:
        await initialize_weibo_cookies()
        ck = await get_weibocookies()
        if ck:
            await send_to_superuser(bot, "Weibo cookies refreshed successfully")
    except Exception:
        sv.logger.error("Failed to initialize or get Weibo cookies")


@on_post_startup
async def initialize_weibo_cookies():
    ck = await get_weibo_cookies_from_local()
    await save_cookies("weibo", ck)


@on_post_startup
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
