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
from .db import list_source_key


USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{1,15}$")
PROFILE_URL_RE = re.compile(r"(?:x|twitter)\.com/([A-Za-z0-9_]{1,15})")
LIST_ID_RE = re.compile(r"(?:x|twitter)\.com/i/lists/(\d+)")

x_list = sv.on_command("x订阅列表", aliases=("xlist",))
x_add = sv.on_command("添加x订阅", aliases=("xadd",), permission=ADMIN)
x_remove = sv.on_command("删除x订阅", aliases=("xremove",), permission=ADMIN)
x_list_list = sv.on_command("x列表订阅列表", aliases=("xlistlist",))
x_list_add = sv.on_command("添加x列表订阅", aliases=("xlistadd",), permission=ADMIN)
x_list_remove = sv.on_command(
    "删除x列表订阅", aliases=("xlistremove",), permission=ADMIN
)


def _username(text: str) -> str | None:
    value = text.strip()
    # Accept a profile/status URL ("https://x.com/name", "x.com/name/status/1")
    # as well as a bare "@name", mirroring the weibo subscription commands.
    if match := PROFILE_URL_RE.search(value):
        value = match.group(1)
    value = value.lstrip("@").lower()
    return value if USERNAME_RE.fullmatch(value) else None


def _list_id(text: str) -> int | None:
    value = text.strip()
    # Accept a bare numeric id or a list URL ("https://x.com/i/lists/123...").
    # twscrape has no slug lookup, so "/<owner>/lists/<slug>" cannot be resolved.
    if match := LIST_ID_RE.search(value):
        value = match.group(1)
    return int(value) if value.isdigit() else None


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


@x_list_list.handle()
async def handle_x_list_list(bot: Bot, target: MsgTarget) -> None:
    scope_key, _, _, _ = _scope(bot, target)
    subscriptions = await store.list_subscriptions_for_scope(scope_key)
    if not subscriptions:
        await UniMessage.text("当前聊天没有 X 列表订阅").send()
        return
    lines = ["X 列表订阅：", *(f"list:{item.list_id}" for item in subscriptions)]
    await UniMessage.text("\n".join(lines)).send()


@x_list_add.handle()
async def handle_x_list_add(
    bot: Bot,
    target: MsgTarget,
    text: str = ParamText(),
) -> None:
    list_id = _list_id(text)
    if list_id is None:
        await UniMessage.text(
            "用法：添加x列表订阅 <列表ID 或 x.com/i/lists/<ID> 链接>"
        ).send()
        return
    scope_key, platform, group_id, target_data = _scope(bot, target)
    added = await store.add_list_subscription(
        scope_key=scope_key,
        platform=platform,
        group_id=group_id,
        target_data=target_data,
        list_id=list_id,
        name=str(list_id),
    )
    await runtime.add_account(list_source_key(list_id))
    message = (
        f"已添加列表 list:{list_id}" if added else f"列表 list:{list_id} 已在订阅列表中"
    )
    await UniMessage.text(message).send()


@x_list_remove.handle()
async def handle_x_list_remove(
    bot: Bot,
    target: MsgTarget,
    text: str = ParamText(),
) -> None:
    list_id = _list_id(text)
    if list_id is None:
        await UniMessage.text(
            "用法：删除x列表订阅 <列表ID 或 x.com/i/lists/<ID> 链接>"
        ).send()
        return
    scope_key, _, _, _ = _scope(bot, target)
    removed = await store.remove_list_subscription(scope_key, list_id)
    await runtime.refresh_accounts()
    message = f"已删除列表 list:{list_id}" if removed else f"未订阅列表 list:{list_id}"
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
    "handle_x_list_add",
    "handle_x_list_list",
    "handle_x_list_remove",
    "handle_x_remove",
    "poll_x",
    "sv",
]
