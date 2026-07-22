"""Telegram event accessors."""

from __future__ import annotations

from typing import Any

from nonebot.adapters import Event

from hoshino.platform.telegram.types import EditedMessageEvent, MessageEvent


def get_event_value(event: Event, name: str, default: Any = None) -> Any:
    return getattr(event, name, default)


def _event_chat(event: Event) -> Any:
    chat = getattr(event, "chat", None)
    if chat is not None:
        return chat
    for name in ("message", "reply_to_message"):
        val = getattr(event, name, None)
        if val is None:
            continue
        chat = getattr(val, "chat", None)
        if chat is not None:
            return chat
    return None


def _event_from_user(event: Event) -> Any:
    for name in ("from_", "from_user", "user", "sender"):
        val = getattr(event, name, None)
        if val is not None:
            return val
    message = getattr(event, "message", None)
    if message is not None:
        for name in ("from_", "from_user"):
            if user := getattr(message, name, None):
                return user
    return None


def get_group_id(event: Event, default: int | None = None) -> int | None:
    chat = _event_chat(event)
    if chat is not None and hasattr(chat, "id"):
        chat_type = getattr(chat, "type", "")
        if chat_type in {"group", "supergroup", "channel"}:
            return int(chat.id)
    return default


def get_chat_id(event: Event, default: int | None = None) -> int | None:
    chat = _event_chat(event)
    if chat is not None and hasattr(chat, "id"):
        return int(chat.id)
    return default


def get_user_id(event: Event, default: int | None = None) -> int | None:
    get_user_id = getattr(event, "get_user_id", None)
    if callable(get_user_id):
        try:
            return int(get_user_id())
        except (TypeError, ValueError):
            pass
    user = _event_from_user(event)
    if user is not None and hasattr(user, "id"):
        return int(user.id)
    return default


def get_event_message(event: Event, default: Any = None) -> Any:
    get_message = getattr(event, "get_message", None)
    if callable(get_message):
        try:
            return get_message()
        except ValueError:
            pass
    return getattr(event, "message", default)


def get_plaintext(event: Event, default: str = "") -> str:
    get_plaintext = getattr(event, "get_plaintext", None)
    if callable(get_plaintext):
        try:
            return get_plaintext()
        except ValueError:
            pass
    message = get_event_message(event)
    if message is None:
        return default
    extract = getattr(message, "extract_plain_text", None)
    if callable(extract):
        return extract()
    return str(getattr(message, "text", None) or getattr(message, "caption", None) or message)


def get_session_id(event: Event, default: str | None = None) -> str | None:
    get_session_id = getattr(event, "get_session_id", None)
    if callable(get_session_id):
        try:
            return get_session_id()
        except ValueError:
            pass
    return default


def get_message_id(event: Event, default: Any = None) -> Any:
    return getattr(event, "message_id", default)


def get_reply_message(event: Event, default: Any = None) -> Any:
    reply = getattr(event, "reply_to_message", None)
    if reply is None:
        return default
    get_message = getattr(reply, "get_message", None)
    if callable(get_message):
        return get_message()
    return getattr(reply, "message", default)


def is_message_event(event: Event) -> bool:
    return isinstance(event, (MessageEvent, EditedMessageEvent))


def is_group_event(event: Event) -> bool:
    return get_group_id(event) is not None


def is_private_event(event: Event) -> bool:
    chat = _event_chat(event)
    if chat is not None and hasattr(chat, "type"):
        return chat.type == "private"
    return False


async def get_forwarded_messages(bot, event: Event) -> list[Any]:
    origin_fields = (
        "forward_origin",
        "forward_from",
        "forward_from_chat",
        "forward_sender_name",
        "forward_date",
    )
    sources = (event, getattr(event, "message", None))
    if any(
        source is not None
        and any(getattr(source, field, None) is not None for field in origin_fields)
        for source in sources
    ):
        current = get_event_message(event)
        return [current] if current is not None else []
    return []
