"""OB11-shaped event accessors — get_group_id, get_user_id, is_group_event, etc."""

from __future__ import annotations

from typing import Any

from nonebot.adapters.onebot.v11 import Event
from nonebot.compat import type_validate_python

from hoshino.platform.ob11.types import Bot, Message
from hoshino.types import MessageId, MessageLike


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


def get_event_message(event: Event, default: Any = None) -> MessageLike | None:
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


def get_message_id(event: Event, default: Any = None) -> MessageId | None:
    return get_event_value(event, "message_id", default)


def get_reply_message(event: Event, default: Any = None) -> MessageLike | None:
    reply = get_event_value(event, "reply")
    if reply is None:
        return default
    return getattr(reply, "message", default)


def get_reply_sender_id(event: Event, default: str | None = None) -> str | None:
    """回复目标的发送者 id（str）；非回复事件返回 default。"""
    reply = get_event_value(event, "reply")
    if reply is None:
        return default
    sender = getattr(reply, "sender", None)
    uid = getattr(sender, "user_id", None)
    return str(uid) if uid is not None else default


def get_reply_message_id(event: Event, default: Any = None) -> MessageId | None:
    """回复目标的消息 id（OB11 供 get_msg 拉取原文用）。"""
    reply = get_event_value(event, "reply")
    if reply is None:
        return default
    return getattr(reply, "message_id", default)


async def fetch_reply_content(bot, event: Event, reply: Any = None) -> Any | None:
    """OB11 reply 段通常只带 id/user_id、不带消息内容，经 ``get_msg`` 拉取原文。

    传入值缺 message_id（如共享层传的是 ``reply.message`` 空内容）时回读事件上的
    Reply 对象；拉取失败返回 None（调用方按无引用处理）。
    """
    if reply is None or getattr(reply, "message_id", None) is None:
        reply = get_event_value(event, "reply")
    if reply is None:
        return None
    if getattr(reply, "message", None):
        return reply.message
    message_id = getattr(reply, "message_id", None)
    if message_id is None:
        return None
    try:
        resp = await bot.get_msg(message_id=message_id)
    except Exception:
        return None
    content = resp.get("message") if isinstance(resp, dict) else None
    if not content:
        return None
    return type_validate_python(Message, content)


def is_message_event(event: Event) -> bool:
    get_type = getattr(event, "get_type", None)
    if not callable(get_type):
        return True
    return get_type() == "message"


def is_group_event(event: Event) -> bool:
    return get_group_id(event) is not None


def is_private_event(event: Event) -> bool:
    return get_group_id(event) is None and get_user_id(event) is not None


async def get_forwarded_messages(bot: Bot, event: Event) -> list[MessageLike]:
    async def expand(message: Message) -> list[Message]:
        result = []
        for segment in message:
            if segment.type != "forward" or not (forward_id := segment.data.get("id")):
                continue
            response = await bot.get_forward_msg(id=forward_id)
            for node in response.get("messages") or response.get("message") or []:
                if content := _forward_content(node):
                    content_message = type_validate_python(Message, content)
                    result.append(content_message)
                    result.extend(await expand(content_message))
        return result

    forwarded = []
    messages = [get_event_message(event)]
    reply = await fetch_reply_content(bot, event)
    if reply is not None:
        messages.append(reply)
    for message in messages:
        if not message:
            continue
        forwarded.extend(await expand(message))
    return forwarded
