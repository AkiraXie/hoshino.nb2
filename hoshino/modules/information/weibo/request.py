import asyncio

from nonebot.adapters import Bot

from hoshino.core.hooks import on_post_startup, on_shutdown, spawn
from hoshino.platform import send_to_superuser
from hoshino.util.command import sucmd
from hoshino.util.cookies import save_cookies

from .db import remove_subscriptions_by_uid, uid_has_any_subscription
from .internal.post_runtime import set_parse_weibo_with_id
from .internal.request_runtime import (
    WeiboRequestError,
    configure_missing_target_handlers,
    get_weibo_list,
    get_weibo_new,
    get_weibocookies,
    missing_weibo_target_worker,
    parse_mapp_weibo,
    parse_weibo_with_id,
)
from .pw import get_weibo_cookies_from_local
from .sub import uid_manager
from .sv import sv

# 解环：向 leaf runtime 注入解析/清理能力，避免函数内 import。
set_parse_weibo_with_id(parse_weibo_with_id)
configure_missing_target_handlers(
    remove_subscriptions_by_uid=remove_subscriptions_by_uid,
    uid_has_any_subscription=uid_has_any_subscription,
    uid_manager=uid_manager,
)

wbck = sucmd("weibocookies", aliases={"wbck", "rfwb"})


@wbck.handle()
async def get_weibocookies_cmd(bot: Bot):
    try:
        await initialize_weibo_cookies()
        ck = await get_weibocookies()
        if ck:
            await send_to_superuser(bot, "Weibo cookies refreshed successfully")
    except Exception:
        sv.logger.exception("Failed to initialize or get Weibo cookies", exception=True)


@on_post_startup
async def initialize_weibo_cookies():
    ck = await get_weibo_cookies_from_local()
    await save_cookies("weibo", ck)


# 后台任务引用：missing_weibo_target_worker 循环 worker，shutdown 时取消
_missing_weibo_target_task: asyncio.Task | None = None


@on_post_startup
async def start_missing_weibo_target_worker() -> None:
    global _missing_weibo_target_task
    _missing_weibo_target_task = spawn(missing_weibo_target_worker())


@on_shutdown
async def stop_missing_weibo_target_worker() -> None:
    if _missing_weibo_target_task:
        _missing_weibo_target_task.cancel()


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
