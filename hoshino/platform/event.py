from __future__ import annotations

from typing import Any

from nonebot.adapters import Event


def get_event_value(event: Event, name: str, default: Any = None) -> Any:
    if hasattr(event, name):
        return getattr(event, name)
    data = getattr(event, "__dict__", {})
    if isinstance(data, dict):
        return data.get(name, default)
    return default


def get_group_id(event: Event, default: int | None = None) -> int | None:
    return get_event_value(event, "group_id", default)


def get_user_id(event: Event, default: int | None = None) -> int | None:
    return get_event_value(event, "user_id", default)


def get_event_message(event: Event, default: Any = None) -> Any:
    get_message = getattr(event, "get_message", None)
    if callable(get_message):
        return get_message()
    return get_event_value(event, "message", default)


def get_plaintext(event: Event, default: str = "") -> str:
    get_plaintext = getattr(event, "get_plaintext", None)
    if callable(get_plaintext):
        return get_plaintext()
    message = get_event_message(event)
    if message is None:
        return default
    return str(message)


def get_session_id(event: Event, default: str | None = None) -> str | None:
    get_session_id = getattr(event, "get_session_id", None)
    if callable(get_session_id):
        return get_session_id()
    return default


def get_message_id(event: Event, default: Any = None) -> Any:
    return get_event_value(event, "message_id", default)


def get_reply_message(event: Event, default: Any = None) -> Any:
    reply = get_event_value(event, "reply")
    if reply is None:
        return default
    return getattr(reply, "message", default)


def is_message_event(event: Event) -> bool:
    get_type = getattr(event, "get_type", None)
    if not callable(get_type):
        return True
    return get_type() == "message"


def is_group_event(event: Event) -> bool:
    return get_group_id(event) is not None


def is_private_event(event: Event) -> bool:
    return get_group_id(event) is None and get_user_id(event) is not None
