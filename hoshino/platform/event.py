"""Adapter-aware event accessors."""

from __future__ import annotations

from typing import Any

from nonebot.adapters import Bot, Event

from hoshino.platform.milky import event as milky_event
from hoshino.platform.milky.types import Event as MilkyEvent
from hoshino.platform.ob11 import event as ob11_event
from hoshino.platform.telegram import event as telegram_event
from hoshino.platform.telegram.types import Event as TelegramEvent


def _backend(event: Event):
    if isinstance(event, MilkyEvent):
        return milky_event
    return telegram_event if isinstance(event, TelegramEvent) else ob11_event


def get_event(event: Event) -> str:
    return str(event.model_dump_json())


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


def get_reply_sender_id(event: Event, default: str | None = None) -> str | None:
    """回复目标的发送者 id（str）；非回复事件返回 default。"""
    return _backend(event).get_reply_sender_id(event, default)


def get_reply_message_id(event: Event, default: Any = None) -> Any:
    """回复目标的消息 id（供 API 拉取原文或匹配 bot 自己消息）。"""
    return _backend(event).get_reply_message_id(event, default)


def is_reply_to_bot(bot: Bot, event: Event) -> bool:
    """当前消息是否为对机器人自己消息的引用回复。"""
    sender = get_reply_sender_id(event)
    return sender is not None and sender == str(bot.self_id)


async def get_reply_content(bot: Bot, event: Event) -> Any | None:
    """回复目标的完整内容；事件内无内容（如 OB11 仅带 id）时经 API 拉取。"""
    reply = get_reply_message(event)
    fetcher = getattr(_backend(event), "fetch_reply_content", None)
    if fetcher is None:
        return reply
    return await fetcher(bot, event, reply)


def is_message_event(event: Event) -> bool:
    return _backend(event).is_message_event(event)


def is_group_event(event: Event) -> bool:
    return _backend(event).is_group_event(event)


def is_private_event(event: Event) -> bool:
    return _backend(event).is_private_event(event)


async def get_forwarded_messages(bot: Bot, event: Event) -> list[Any]:
    getter = getattr(_backend(event), "get_forwarded_messages", None)
    return await getter(bot, event) if getter else []
