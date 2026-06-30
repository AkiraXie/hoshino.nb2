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


def is_message_event(event: Event) -> bool:
    get_type = getattr(event, "get_type", None)
    if not callable(get_type):
        return True
    return get_type() == "message"


def is_group_event(event: Event) -> bool:
    return get_group_id(event) is not None


def is_private_event(event: Event) -> bool:
    return get_group_id(event) is None and get_user_id(event) is not None
