"""Hoshino 常用类型集中 re-export。导入此模块不触发 NoneBot 运行时。"""

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
