"""Hoshino 常用类型集中 re-export。导入此模块不触发 NoneBot 运行时。"""
from typing import TYPE_CHECKING

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
from hoshino.platform.ob11.types import Bot as OneBotV11Bot
from hoshino.platform.ob11.types import Event as OneBotV11Event
from hoshino.platform.ob11.types import Message as OneBotV11Message
from hoshino.platform.ob11.types import MessageSegment as OneBotV11MessageSegment
from nonebot.adapters import MessageTemplate as MessageTemplate

if TYPE_CHECKING:
    from typing import Any, Callable, Type as _Type
    from nonebot.matcher import Matcher as _OrigMatcher
    from hoshino.platform.ob11.types import Bot as _OrigBot

    class Matcher(_OrigMatcher):
        @classmethod
        def got(
            cls: _Type[Matcher],
            key: str,
            prompt: str | OneBotV11Message | OneBotV11MessageSegment | MessageTemplate | None = None,
            parameterless: list | None = None,
            args_parser: T_Handler | None = None,
        ) -> Callable[[T_Handler], T_Handler]: ...

    class OneBotV11Bot(_OrigBot):
        async def send(
            self,
            event: OneBotV11Event,
            message: str | OneBotV11Message | OneBotV11MessageSegment,
            at_sender: bool = False,
            call_header: bool = False,
            **kwargs,
        ) -> Any: ...
