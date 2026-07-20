"""Adapter-aware event accessors."""

from __future__ import annotations

from typing import Any

from nonebot.adapters import Event

from hoshino.platform.milky import event as milky_event
from hoshino.platform.milky.types import Event as MilkyEvent
from hoshino.platform.ob11 import event as ob11_event
from hoshino.platform.telegram import event as telegram_event
from hoshino.platform.telegram.types import Event as TelegramEvent


def _backend(event: Event):
    if isinstance(event, MilkyEvent):
        return milky_event
    return telegram_event if isinstance(event, TelegramEvent) else ob11_event


def get_event_value(event: Event, name: str, default: Any = None) -> Any:
    return _backend(event).get_event_value(event, name, default)


def get_group_id(event: Event, default: int | None = None) -> int | None:
    return _backend(event).get_group_id(event, default)


def get_user_id(event: Event, default: int | None = None) -> int | None:
    return _backend(event).get_user_id(event, default)


def get_event_message(event: Event, default: Any = None) -> Any:
    return _backend(event).get_event_message(event, default)


def get_plaintext(event: Event, default: str = "") -> str:
    return _backend(event).get_plaintext(event, default)


def get_session_id(event: Event, default: str | None = None) -> str | None:
    return _backend(event).get_session_id(event, default)


def get_message_id(event: Event, default: Any = None) -> Any:
    return _backend(event).get_message_id(event, default)


def get_reply_message(event: Event, default: Any = None) -> Any:
    return _backend(event).get_reply_message(event, default)


def is_message_event(event: Event) -> bool:
    return _backend(event).is_message_event(event)


def is_group_event(event: Event) -> bool:
    return _backend(event).is_group_event(event)


def is_private_event(event: Event) -> bool:
    return _backend(event).is_private_event(event)
