"""Shared Hoshino type aliases."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypeAlias

if TYPE_CHECKING:
    from nonebot_plugin_alconna.uniseg import UniMessage
    from hoshino.platform.ob11.types import Message as OB11Message
    from hoshino.platform.ob11.types import MessageSegment as OB11Segment

    T_Message: TypeAlias = str | UniMessage | OB11Message | OB11Segment
else:
    T_Message: TypeAlias = Any

MessageLike = T_Message
