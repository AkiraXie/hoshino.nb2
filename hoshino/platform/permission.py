"""Adapter-aware permission predicates."""

from __future__ import annotations

from typing import Any

from nonebot.adapters import Bot, Event
from nonebot.permission import Permission, SUPERUSER

from hoshino.platform.event import (
    get_group_id,
    get_user_id,
    is_group_event,
    is_message_event,
    is_private_event,
)
from hoshino.platform.telegram.bot import get_chat_member_status
from hoshino.platform.telegram.types import Event as TelegramEvent


def _get_value(source: Any, name: str) -> Any:
    if source is None:
        return None
    if isinstance(source, dict):
        return source.get(name)
    return getattr(source, name, None)


def _sender_role(event: Event) -> str:
    sender = _get_value(event, "sender")
    role = _get_value(sender, "role")
    return str(role or "").lower()


async def _group(event: Event) -> bool:
    return is_message_event(event) and is_group_event(event)


async def _private(event: Event) -> bool:
    return is_message_event(event) and is_private_event(event)


async def _telegram_role(bot: Bot, event: Event) -> str:
    group_id = get_group_id(event)
    user_id = get_user_id(event)
    if group_id is None or user_id is None:
        return ""
    try:
        return await get_chat_member_status(bot, group_id, user_id)
    except Exception:
        return ""


async def _group_admin(bot: Bot, event: Event) -> bool:
    if not await _group(event):
        return False
    if isinstance(event, TelegramEvent):
        return await _telegram_role(bot, event) in {"administrator", "creator"}
    return _sender_role(event) in {"admin", "owner"}


async def _group_owner(bot: Bot, event: Event) -> bool:
    if not await _group(event):
        return False
    if isinstance(event, TelegramEvent):
        return await _telegram_role(bot, event) == "creator"
    return _sender_role(event) == "owner"


GROUP = Permission(_group)
PRIVATE = Permission(_private)
GROUP_ADMIN = Permission(_group_admin)
GROUP_OWNER = Permission(_group_owner)

ADMIN = SUPERUSER | GROUP_ADMIN | GROUP_OWNER
PADMIN = SUPERUSER | GROUP_ADMIN | GROUP_OWNER | PRIVATE
OWNER = SUPERUSER | GROUP_OWNER
POWNER = SUPERUSER | GROUP_OWNER | PRIVATE
NORMAL = SUPERUSER | GROUP | PRIVATE

__all__ = [
    "ADMIN",
    "GROUP",
    "GROUP_ADMIN",
    "GROUP_OWNER",
    "NORMAL",
    "OWNER",
    "PADMIN",
    "POWNER",
    "PRIVATE",
]

