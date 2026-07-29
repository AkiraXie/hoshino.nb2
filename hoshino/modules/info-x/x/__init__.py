"""X subscriptions, polling and cross-adapter delivery."""

from __future__ import annotations

import re

from nonebot.adapters import Bot

from hoshino.command import MsgTarget, UniMessage
import asyncio

from hoshino.core.hooks import on_post_startup, on_serial_startup, on_shutdown
from hoshino.core.schedule import scheduled_job
from hoshino.platform import dump_target, platform_key, target_scope_key
from hoshino.platform.depends import ParamText
from hoshino.platform.permission import ADMIN

from . import reaction as reaction
from .sv import sv
from .runtime import runtime, store


USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{1,15}$")

x_list = sv.on_command("x订阅列表", aliases=("xlist",))
x_add = sv.on_command("添加x订阅", aliases=("xadd",), permission=ADMIN)
x_remove = sv.on_command("删除x订阅", aliases=("xremove",), permission=ADMIN)


def _username(text: str) -> str | None:
    value = text.strip().lstrip("@").lower()
    return value if USERNAME_RE.fullmatch(value) else None


def _scope(bot: Bot, target: MsgTarget) -> tuple[str, str, int, str]:
    platform = platform_key(bot)
    scope_key = target_scope_key(target, platform=platform)
    group_id = int(target.parent_id or target.id)
    return scope_key, platform, group_id, dump_target(target)


@x_list.handle()
async def handle_x_list(bot: Bot, target: MsgTarget) -> None:
    scope_key, _, _, _ = _scope(bot, target)
    subscriptions = await store.subscriptions_for_scope(scope_key)
    if not subscriptions:
        await UniMessage.text("当前聊天没有 X 订阅").send()
        return
    lines = ["X 订阅：", *(f"@{item.username}" for item in subscriptions)]
    await UniMessage.text("\n".join(lines)).send()


@x_add.handle()
async def handle_x_add(
    bot: Bot,
    target: MsgTarget,
    text: str = ParamText(),
) -> None:
    username = _username(text)
    if username is None:
        await UniMessage.text("用法：添加x订阅 <用户名>").send()
        return
    scope_key, platform, group_id, target_data = _scope(bot, target)
    added = await store.add_subscription(
        scope_key=scope_key,
        platform=platform,
        group_id=group_id,
        target_data=target_data,
        username=username,
        name=username,
    )
    await runtime.add_account(username)
    message = f"已添加 @{username}" if added else f"@{username} 已在订阅列表中"
    await UniMessage.text(message).send()


@x_remove.handle()
async def handle_x_remove(
    bot: Bot,
    target: MsgTarget,
    text: str = ParamText(),
) -> None:
    username = _username(text)
    if username is None:
        await UniMessage.text("用法：删除x订阅 <用户名>").send()
        return
    scope_key, _, _, _ = _scope(bot, target)
    removed = await store.remove_subscription(scope_key, username)
    await runtime.refresh_accounts()
    message = f"已删除 @{username}" if removed else f"未订阅 @{username}"
    await UniMessage.text(message).send()


@on_serial_startup
async def initialize_x() -> None:
    await runtime.bootstrap()


@on_shutdown
async def shutdown_x() -> None:
    await runtime.shutdown()


@scheduled_job("interval", seconds=3, jitter=0.2, id="获取X更新")
async def poll_x() -> None:
    await runtime.fetch_next_update()


async def _x_dispatch_worker() -> None:
    while True:
        try:
            sent = await runtime.dispatch_pending()
        except Exception:
            sv.logger.exception("X dispatch worker error")
            sent = 0
        await asyncio.sleep(0 if sent else 0.5)


@on_post_startup
async def start_x_dispatch_worker() -> None:
    asyncio.create_task(_x_dispatch_worker())


__all__ = [
    "handle_x_add",
    "handle_x_list",
    "handle_x_remove",
    "poll_x",
    "sv",
]
