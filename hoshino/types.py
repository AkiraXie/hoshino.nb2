"""Hoshino 常用类型集中 re-export。导入此模块不触发 NoneBot 运行时。"""
from __future__ import annotations
from typing import TYPE_CHECKING, Union

from nonebot.adapters import Bot as Bot
from nonebot.adapters import Event as Event
from nonebot.typing import T_Handler as T_Handler
from nonebot.typing import T_State as T_State
from nonebot.params import Depends as Depends
from nonebot.params import BotParam as BotParam
from nonebot.params import EventParam as EventParam
from nonebot.params import StateParam as StateParam
from nonebot.params import MatcherParam as MatcherParam
from nonebot.params import DependParam as DependParam
from nonebot.dependencies import Dependent as Dependent
from nonebot.matcher import Matcher as Matcher
from nonebot.matcher import current_bot as current_bot
from nonebot.matcher import current_event as current_event
from nonebot.adapters import MessageTemplate as MessageTemplate

if TYPE_CHECKING:
    from typing import Any
    from hoshino.platform.ob11.types import Bot as OB11Bot
    from hoshino.platform.ob11.types import Event as OB11Event
    from hoshino.platform.ob11.types import Message as OB11Message
    from hoshino.platform.ob11.types import MessageSegment as OB11Segment

    class OneBotV11Bot(OB11Bot):
        async def send(
            self,
            event: OB11Event,
            message: str | OB11Message | OB11Segment,
            at_sender: bool = False,
            call_header: bool = False,
            **kwargs,
        ) -> Any: ...


# 统一消息类型 — 可接收任意平台的消息对象（运行时为 ForwardRef）
T_Message = Union[str, "UniMessage", "OB11Message", "OB11Segment"]  # noqa: F821
MessageLike = T_Message
