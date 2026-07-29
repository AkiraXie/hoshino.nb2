"""OB11-shaped event accessors — get_group_id, get_user_id, is_group_event, etc."""

from __future__ import annotations

from typing import Any

from nonebot.adapters.onebot.v11 import Event
from nonebot.compat import type_validate_python

from hoshino.platform.ob11.types import Bot, Message


def _forward_content(node: Any) -> Any:
    if not isinstance(node, dict):
        return node
    return node.get("content") or node.get("data", {}).get("content")


def get_event_value(event: Event, name: str, default: Any = None) -> Any:
    if hasattr(event, name):
        return getattr(event, name)
    data = getattr(event, "__dict__", {})
    if isinstance(data, dict):
        return data.get(name, default)
    return default


def get_event(event: Event) -> str:
    return str(event.model_dump_json())


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


async def get_forwarded_messages(bot: Bot, event: Event) -> list[Message]:
    async def expand(message: Message) -> list[Message]:
        result = []
        for segment in message:
            if segment.type != "forward" or not (
                forward_id := segment.data.get("id")
            ):
                continue
            response = await bot.get_forward_msg(id=forward_id)
            for node in response.get("messages") or response.get("message") or []:
                if content := _forward_content(node):
                    content_message = type_validate_python(Message, content)
                    result.append(content_message)
                    result.extend(await expand(content_message))
        return result

    forwarded = []
    for message in (get_event_message(event), get_reply_message(event)):
        if not message:
            continue
        forwarded.extend(await expand(message))
    return forwarded
