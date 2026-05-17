"""Hoshino 常用类型集中 re-export。导入此模块不触发 NoneBot 运行时。"""
from typing import TYPE_CHECKING

from nonebot.typing import T_Handler, T_State
from nonebot.params import Depends, BotParam, EventParam, StateParam, MatcherParam, DependParam
from nonebot.dependencies import Dependent
from nonebot.matcher import Matcher, current_bot, current_event
from nonebot.adapters.onebot.v11 import Adapter, Bot
from nonebot.adapters.onebot.v11.utils import escape
from .message import MessageSegment, Message, MessageTemplate
from .event import Event

if TYPE_CHECKING:
    from typing import Any, Callable, Optional, Type as _Type, Union as _Union

    # 告诉 IDE：Matcher.got 在 bootstrap 时被 patch，多出 args_parser 等参数
    class Matcher(Matcher):
        @classmethod
        def got(
            cls: _Type[Matcher],
            key: str,
            prompt: Optional[_Union[str, Message, MessageSegment, MessageTemplate]] = None,
            parameterless: Optional[list] = None,
            args_parser: Optional[T_Handler] = None,
        ) -> Callable[[T_Handler], T_Handler]: ...

    # 告诉 IDE：Bot.send 在 bootstrap 时被 patch，支持 at_sender/call_header
    class Bot(Bot):
        async def send(
            self,
            event: Event,
            message: _Union[str, Message, MessageSegment],
            at_sender: bool = False,
            call_header: bool = False,
            **kwargs,
        ) -> Any: ...
