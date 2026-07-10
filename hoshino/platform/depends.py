"""Adapter-aware dependency providers — backed by nonebot-plugin-uninfo."""

from __future__ import annotations

from typing import Any

from nonebot.adapters import Bot, Event
from nonebot.params import Depends
from nonebot_plugin_uninfo import SceneType, get_session

from hoshino.platform.bot import get_group_member_info
from hoshino.platform.event import (
    get_event_message,
    get_plaintext,
)


def GroupID() -> int | None:
    async def _(event: Event) -> int | None:
        session = await get_session(bot=None, event=event)
        if session and session.scene.type == SceneType.GROUP:
            return int(session.scene.id)
        return None

    return Depends(_)


def SenderID() -> int | None:
    async def _(event: Event) -> int | None:
        session = await get_session(bot=None, event=event)
        if session:
            return int(session.user.id)
        return None

    return Depends(_)


def PlainText() -> str:
    async def _(event: Event) -> str:
        return get_plaintext(event)

    return Depends(_)


def EventMessage(default: Any = None) -> Any:
    async def _(event: Event) -> Any:
        return get_event_message(event, default)

    return Depends(_)


def RawMessage(default: str = "") -> str:
    async def _(event: Event) -> str:
        if raw_message := getattr(event, "raw_message", None):
            return str(raw_message)
        return get_plaintext(event, default)

    return Depends(_)


def ReplyMessage() -> Any:
    async def _(event: Event) -> Any:
        from hoshino.platform.event import get_reply_message

        return get_reply_message(event)

    return Depends(_)


def MessageID() -> int | None:
    async def _(event: Event) -> int | None:
        from hoshino.platform.event import get_message_id

        return get_message_id(event)

    return Depends(_)


def GroupMemberName(default: str = "") -> str:
    async def _(
        bot: Bot,
        group_id: int | None = GroupID(),
        user_id: int | None = SenderID(),
    ) -> str:
        if group_id is None or user_id is None:
            return default
        info = await get_group_member_info(bot, group_id, user_id)
        for key in ("card", "nickname"):
            if value := info.get(key):
                return str(value)
        return default

    return Depends(_)
