"""Hoshino 常用类型集中 re-export。导入此模块不触发 NoneBot 运行时。"""
from nonebot.typing import T_Handler, T_State
from nonebot.params import Depends, BotParam, EventParam, StateParam, MatcherParam, DependParam
from nonebot.dependencies import Dependent
from nonebot.matcher import Matcher, current_bot, current_event
from nonebot.adapters.onebot.v11 import Adapter, Bot
from nonebot.adapters.onebot.v11.utils import escape
from .message import MessageSegment, Message, MessageTemplate
from .event import Event
