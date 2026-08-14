"""Shared Hoshino type aliases."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypeAlias

if TYPE_CHECKING:
    from nonebot_plugin_alconna.uniseg import UniMessage

    from hoshino.platform.milky.types import Message as MilkyMessage
    from hoshino.platform.milky.types import MessageSegment as MilkySegment
    from hoshino.platform.ob11.types import Message as OB11Message
    from hoshino.platform.ob11.types import MessageSegment as OB11Segment
    from hoshino.platform.telegram.types import Message as TelegramMessage
    from hoshino.platform.telegram.types import MessageSegment as TelegramSegment

    T_Message: TypeAlias = (
        str
        | UniMessage
        | OB11Message
        | OB11Segment
        | TelegramMessage
        | TelegramSegment
        | MilkyMessage
        | MilkySegment
    )
else:
    T_Message: TypeAlias = Any

MessageLike = T_Message

# 跨 adapter 统一的消息/会话 id 形态（OB11/Milky/Telegram 均为 int，保留 str 兼容）。
MessageId: TypeAlias = int | str
