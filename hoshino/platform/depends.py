"""Adapter-aware dependency providers — backed by nonebot-plugin-uninfo."""

from __future__ import annotations

from typing import Any

from nonebot.adapters import Bot, Event
from nonebot.params import Depends
from nonebot_plugin_uninfo import get_session

from hoshino.platform.event import (
    get_event_message,
    get_message_id,
    get_plaintext,
    get_reply_message,
)


def GroupID() -> int | None:
    async def _(bot: Bot, event: Event) -> int | None:
        session = await get_session(bot, event)
        if session and session.scene.is_group:
            return int(session.scene.id)
        return None

    return Depends(_)


def SenderID() -> int | None:
    async def _(bot: Bot, event: Event) -> int | None:
        session = await get_session(bot, event)
        return int(session.user.id) if session else None

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
        return get_reply_message(event)

    return Depends(_)


def MessageID() -> int | None:
    async def _(event: Event) -> int | None:
        return get_message_id(event)

    return Depends(_)


def LightAppJsonPayload():
    """Unified DI — extract JSON/light_app payload from OB11 or Milky message.

    Returns the parsed ``dict`` from the first matching segment,
    or ``None`` when no light_app/json mini-program segment is present.

    OB11  messages use ``type="json"``  → ``s.data["data"]`` (JSON string).
    Milky messages use ``type="light_app"`` → ``s.data["json_payload"]`` (JSON string).
    """

    async def _(event: Event) -> dict | None:
        import json as _json

        msg = get_event_message(event)
        if msg is None:
            return None
        for seg in msg:
            stype = getattr(seg, "type", None)
            if stype not in ("json", "light_app"):
                continue
            data = getattr(seg, "data", None)
            if not isinstance(data, dict):
                continue
            # Milky: s.data["json_payload"], OB11: s.data["data"]
            raw = data.get("json_payload") or data.get("data")
            if not raw:
                continue
            try:
                return _json.loads(raw)
            except (_json.JSONDecodeError, TypeError):
                return None
        return None

    return Depends(_)


def GroupMemberName(default: str = "") -> str:
    async def _(bot: Bot, event: Event) -> str:
        session = await get_session(bot, event)
        if session is None:
            return default
        member = session.member
        for value in (
            member.nick if member else None,
            session.user.nick,
            session.user.name,
        ):
            if value:
                return str(value)
        return default

    return Depends(_)
