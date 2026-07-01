"""OB11-shaped dependency providers."""

from __future__ import annotations

from typing import Any

from nonebot.adapters import Bot, Event
from nonebot.params import Depends

from hoshino.platform.ob11.bot import get_group_member_info


def GroupID() -> int | None:
    """当前 OB11 群号，私聊或无群号返回 None。"""

    async def _(event: Event) -> int | None:
        return getattr(event, "group_id", None)

    return Depends(_)


def SenderID() -> int | None:
    """当前 OB11 发送者 user_id。"""

    async def _(event: Event) -> int | None:
        return getattr(event, "user_id", None)

    return Depends(_)


def PlainText() -> str:
    """当前 OB11 消息纯文本。"""

    async def _(event: Event) -> str:
        get_plaintext = getattr(event, "get_plaintext", None)
        if callable(get_plaintext):
            return get_plaintext()
        msg = getattr(event, "get_message", None)
        if callable(msg):
            return str(msg())
        return ""

    return Depends(_)


def EventMessage(default: Any = None) -> Any:
    """当前 OB11 事件消息对象。"""

    async def _(event: Event) -> Any:
        get_message = getattr(event, "get_message", None)
        if callable(get_message):
            return get_message()
        return default

    return Depends(_)


def RawMessage(default: str = "") -> str:
    """当前 OB11 raw_message。"""

    async def _(event: Event) -> str:
        return str(getattr(event, "raw_message", default))

    return Depends(_)


def ReplyMessage() -> Any:
    """当前 OB11 回复消息对象，无回复返回 None。"""

    async def _(event: Event) -> Any:
        reply = getattr(event, "reply", None)
        return reply.message if reply else None

    return Depends(_)


def MessageID() -> int | None:
    """当前 OB11 消息 ID，无则返回 None。"""

    async def _(event: Event) -> int | None:
        return getattr(event, "message_id", None)

    return Depends(_)


def GroupMemberName(default: str = "") -> str:
    """当前发送者在 OB11 群内的名片/昵称，失败时返回 default。"""

    async def _(
        bot: Bot,
        group_id: int | None = GroupID(),
        user_id: int | None = SenderID(),
    ) -> str:
        if group_id is None or user_id is None:
            return default
        info = await get_group_member_info(
            bot,
            group_id=group_id,
            user_id=user_id,
            no_cache=True,
        )
        for key in ("card", "nickname"):
            value = info.get(key)
            if value:
                return str(value)
        return default

    return Depends(_)
