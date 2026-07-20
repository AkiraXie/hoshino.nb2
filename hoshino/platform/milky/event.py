"""Milky event accessors exposed to the common platform facade."""

from __future__ import annotations

from typing import Any

from nonebot.adapters import Event

from hoshino.platform.milky.types import (
    GroupMessageEvent,
    MessageEvent,
)


def _data_value(event: Event, name: str, default: Any = None) -> Any:
    data = getattr(event, "data", None)
    if isinstance(data, dict):
        return data.get(name, default)
    return getattr(data, name, default)


def get_event_value(event: Event, name: str, default: Any = None) -> Any:
    """Read a canonical field from a Milky event or its data model."""

    value = getattr(event, name, None)
    if value is not None:
        return value
    return _data_value(event, name, default)


def get_group_id(event: Event, default: int | None = None) -> int | None:
    data = getattr(event, "data", None)
    if isinstance(event, MessageEvent):
        if data.message_scene not in {"group", "temp"}:
            return default
        group = getattr(data, "group", None)
        group_id = getattr(group, "group_id", None) if group else None
        return int(group_id if group_id is not None else data.peer_id)
    group_id = _data_value(event, "group_id")
    return int(group_id) if group_id is not None else default


def get_user_id(event: Event, default: int | None = None) -> int | None:
    getter = getattr(event, "get_user_id", None)
    if callable(getter):
        try:
            return int(getter())
        except (TypeError, ValueError):
            pass
    for name in ("sender_id", "user_id", "operator_id", "initiator_id"):
        value = _data_value(event, name)
        if value is not None:
            return int(value)
    return default


def get_event_message(event: Event, default: Any = None) -> Any:
    getter = getattr(event, "get_message", None)
    if callable(getter):
        try:
            return getter()
        except (TypeError, ValueError):
            pass
    return _data_value(event, "message", default)


def get_plaintext(event: Event, default: str = "") -> str:
    getter = getattr(event, "get_plaintext", None)
    if callable(getter):
        try:
            return str(getter())
        except (TypeError, ValueError):
            pass
    message = get_event_message(event)
    if message is None:
        return default
    extract = getattr(message, "extract_plain_text", None)
    return str(extract() if callable(extract) else message)


def get_session_id(event: Event, default: str | None = None) -> str | None:
    getter = getattr(event, "get_session_id", None)
    if callable(getter):
        try:
            return str(getter())
        except (TypeError, ValueError):
            pass
    return default


def get_message_id(event: Event, default: Any = None) -> Any:
    value = getattr(event, "message_id", None)
    if value is not None:
        return value
    return _data_value(event, "message_seq", default)


def get_reply_message(event: Event, default: Any = None) -> Any:
    reply = getattr(event, "reply", None)
    if reply is None:
        return default
    return getattr(reply, "message", reply)


def is_message_event(event: Event) -> bool:
    return isinstance(event, MessageEvent)


def is_group_event(event: Event) -> bool:
    return get_group_id(event) is not None


def is_private_event(event: Event) -> bool:
    return bool(getattr(event, "is_private", False)) and not isinstance(
        event, GroupMessageEvent
    )


__all__ = [
    "get_event_message",
    "get_event_value",
    "get_group_id",
    "get_message_id",
    "get_plaintext",
    "get_reply_message",
    "get_session_id",
    "get_user_id",
    "is_group_event",
    "is_message_event",
    "is_private_event",
]
