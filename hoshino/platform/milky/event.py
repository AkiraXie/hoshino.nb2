"""Milky event accessors exposed to the common platform facade."""

from __future__ import annotations

from typing import Any

from nonebot.adapters import Event

from hoshino.types import MessageId, MessageLike

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


def get_event_message(event: Event, default: Any = None) -> MessageLike | None:
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


def get_message_id(event: Event, default: Any = None) -> MessageId | None:
    value = getattr(event, "message_id", None)
    if value is not None:
        return value
    return _data_value(event, "message_seq", default)


def get_reply_message(event: Event, default: Any = None) -> MessageLike | None:
    reply = getattr(event, "reply", None)
    if reply is None:
        return default
    return getattr(reply, "message", reply)


def get_reply_sender_id(event: Event, default: str | None = None) -> str | None:
    """回复目标的发送者 id（str）；非回复事件返回 default。"""
    reply = getattr(event, "reply", None)
    if reply is None:
        return default
    sender_id = getattr(reply, "sender_id", None)
    return str(sender_id) if sender_id is not None else default


def get_reply_message_id(event: Event, default: Any = None) -> MessageId | None:
    """回复目标的消息序列号（Milky 会话内序列）。"""
    reply = getattr(event, "reply", None)
    if reply is None:
        return default
    seq = getattr(reply, "message_seq", None)
    return str(seq) if seq is not None else default


def is_message_event(event: Event) -> bool:
    return isinstance(event, MessageEvent)


def is_group_event(event: Event) -> bool:
    return get_group_id(event) is not None


def is_private_event(event: Event) -> bool:
    return bool(getattr(event, "is_private", False)) and not isinstance(
        event, GroupMessageEvent
    )


async def _expand_forward_segments(bot, message) -> list[Any]:
    forwarded = []
    for segment in message or []:
        if segment.type != "forward":
            continue
        if messages := segment.data.get("messages"):
            for node in messages:
                content = getattr(node, "segments", None)
                if content is not None:
                    forwarded.append(content)
                    forwarded.extend(await _expand_forward_segments(bot, content))
        elif forward_id := segment.data.get("forward_id"):
            for node in await bot.get_forwarded_messages(forward_id=forward_id):
                content = node.message
                forwarded.append(content)
                forwarded.extend(await _expand_forward_segments(bot, content))
    return forwarded


async def get_forwarded_messages(bot, event: Event) -> list[MessageLike]:
    forwarded = []
    for message in (get_event_message(event), get_reply_message(event)):
        forwarded.extend(await _expand_forward_segments(bot, message))
    return forwarded


__all__ = [
    "get_event_message",
    "get_forwarded_messages",
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
