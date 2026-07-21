"""Adapter-aware dependency providers — backed by nonebot-plugin-uninfo."""

from __future__ import annotations

import json
from typing import Any

from arclet.alconna import Arparma
from nonebot.adapters import Bot, Event
from nonebot.params import Depends
from nonebot_plugin_alconna import AlconnaMatches
from nonebot_plugin_alconna.uniseg import UniMessage
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


def ParamMessage(default: UniMessage | None = None) -> UniMessage:
    """Inject the complete ``Service.on_command`` argument message."""

    async def _(matches: Arparma = AlconnaMatches()) -> UniMessage:
        value = matches.all_matched_args.get("text")
        return UniMessage(value) if value else default or UniMessage()

    return Depends(_)


def ParamText(default: str = "") -> str:
    """Inject the complete plain-text argument after a service command."""

    async def _(matches: Arparma = AlconnaMatches()) -> str:
        value = matches.all_matched_args.get("text")
        return UniMessage(value).extract_plain_text() if value else default

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


def get_light_app_json_payload(event: Event) -> dict[str, Any] | None:
    """Return the first valid mini-program JSON object in an adapter message."""

    message = get_event_message(event)
    if message is None:
        return None
    for segment in message:
        segment_type = getattr(segment, "type", None)
        if segment_type not in {"json", "light_app"}:
            continue
        data = getattr(segment, "data", None)
        if not isinstance(data, dict):
            continue
        field = "json_payload" if segment_type == "light_app" else "data"
        payload = data.get(field)
        if not isinstance(payload, str):
            continue
        try:
            decoded = json.loads(payload)
        except json.JSONDecodeError:
            return None
        return decoded if isinstance(decoded, dict) else None
    return None


def LightAPPJsonPayload() -> Any:
    """Inject JSON from legacy ``json`` or Milky ``light_app`` segments.

    Returns the parsed JSON object from the first matching segment,
    or ``None`` when no light_app/json mini-program segment is present.

    Legacy adapters use ``type="json"`` and ``data["data"]``. Milky uses
    ``type="light_app"`` and ``data["json_payload"]``.
    """

    return Depends(get_light_app_json_payload)


LightAppJsonPayload = LightAPPJsonPayload


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
