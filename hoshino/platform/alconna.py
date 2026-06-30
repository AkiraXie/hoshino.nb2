from __future__ import annotations

from typing import Any

from nonebot.adapters import Event
from nonebot.params import Depends
from nonebot_plugin_alconna import Alconna as Alconna
from nonebot_plugin_alconna import AlconnaMatches as AlconnaMatches
from nonebot_plugin_alconna import AlconnaResult as AlconnaResult
from nonebot_plugin_alconna import Args as Args
from nonebot_plugin_alconna import CommandMeta as CommandMeta
from nonebot_plugin_alconna import Match as Match
from nonebot_plugin_alconna import MsgId as MsgId
from nonebot_plugin_alconna import MsgTarget as MsgTarget
from nonebot_plugin_alconna import Option as Option
from nonebot_plugin_alconna import Query as Query
from nonebot_plugin_alconna import Reply as Reply
from nonebot_plugin_alconna import Subcommand as Subcommand
from nonebot_plugin_alconna import UniMsg as UniMsg
from nonebot_plugin_alconna.uniseg import UniMessage

UniTarget = MsgTarget


def uni_text(text: str) -> UniMessage:
    return UniMessage.text(text)


def uni_image(file: Any) -> UniMessage:
    if isinstance(file, bytes):
        return UniMessage.image(raw=file)
    if isinstance(file, str) and file.startswith(("http://", "https://")):
        return UniMessage.image(url=file)
    return UniMessage.image(path=file)


def uni_video(file: Any) -> UniMessage:
    if isinstance(file, bytes):
        return UniMessage.video(raw=file)
    if isinstance(file, str) and file.startswith(("http://", "https://")):
        return UniMessage.video(url=file)
    return UniMessage.video(path=file)


# ── Custom Depends for non-Alconna handlers ──


def GroupID() -> int | None:
    """DI：当前事件的群号，私聊或无群号返回 None"""
    async def _(event: Event) -> int | None:
        return getattr(event, "group_id", None)
    return Depends(_)


def SenderID() -> int | None:
    """DI：当前事件发送者的 user_id"""
    async def _(event: Event) -> int | None:
        return getattr(event, "user_id", None)
    return Depends(_)


def PlainText() -> str:
    """DI：消息纯文本"""
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
    """DI：当前事件消息对象"""
    async def _(event: Event) -> Any:
        get_message = getattr(event, "get_message", None)
        if callable(get_message):
            return get_message()
        return default
    return Depends(_)


def RawMessage(default: str = "") -> str:
    """DI：当前事件 raw_message"""
    async def _(event: Event) -> str:
        return str(getattr(event, "raw_message", default))
    return Depends(_)


def ReplyMessage() -> Any:
    """DI：回复消息对象，无回复返回 None"""
    async def _(event: Event) -> Any:
        reply = getattr(event, "reply", None)
        return reply.message if reply else None
    return Depends(_)


def MessageID() -> int | None:
    """DI：当前消息 ID，无则返回 None"""
    async def _(event: Event) -> int | None:
        return getattr(event, "message_id", None)
    return Depends(_)
