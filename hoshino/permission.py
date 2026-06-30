from __future__ import annotations

from typing import Any

from nonebot.adapters import Event
from nonebot.permission import SUPERUSER, Permission, USER


def _get_value(source: Any, name: str) -> Any:
    if source is None:
        return None
    if isinstance(source, dict):
        return source.get(name)
    if hasattr(source, name):
        return getattr(source, name)
    get = getattr(source, "get", None)
    if callable(get):
        return get(name)
    return None


def _get_sender(event: Event) -> Any:
    sender = _get_value(event, "sender")
    if sender is not None:
        return sender
    raw_event = _get_value(event, "original_event")
    return _get_value(raw_event, "sender")


def _is_message_event(event: Event) -> bool:
    get_type = getattr(event, "get_type", None)
    if not callable(get_type):
        return True
    return get_type() == "message"


async def _group(event: Event) -> bool:
    if not _is_message_event(event):
        return False
    return (
        _get_value(event, "group_id") is not None
        or _get_value(event, "guild_id") is not None
        or _get_value(event, "channel_id") is not None
    )


async def _private(event: Event) -> bool:
    if not _is_message_event(event):
        return False
    return not await _group(event) and _get_value(event, "user_id") is not None


def _sender_role(event: Event) -> str:
    role = _get_value(_get_sender(event), "role")
    return str(role or "").lower()


async def _group_admin(event: Event) -> bool:
    return await _group(event) and _sender_role(event) in {"admin", "owner"}


async def _group_owner(event: Event) -> bool:
    return await _group(event) and _sender_role(event) == "owner"


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
    "Permission",
    "SUPERUSER",
    "USER",
]
