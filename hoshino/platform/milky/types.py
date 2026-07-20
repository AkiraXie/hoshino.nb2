"""Milky adapter types kept behind the platform boundary."""

from nonebot.adapters.milky import Adapter as Adapter
from nonebot.adapters.milky import Bot as Bot
from nonebot.adapters.milky import Event as Event
from nonebot.adapters.milky import Message as Message
from nonebot.adapters.milky import MessageSegment as MessageSegment
from nonebot.adapters.milky.event import FriendMessageEvent as FriendMessageEvent
from nonebot.adapters.milky.event import GroupMessageEvent as GroupMessageEvent
from nonebot.adapters.milky.event import (
    GroupMessageReactionEvent as GroupMessageReactionEvent,
)
from nonebot.adapters.milky.event import MessageEvent as MessageEvent
from nonebot.adapters.milky.event import NoticeEvent as NoticeEvent
from nonebot.adapters.milky.event import TempMessageEvent as TempMessageEvent

MilkyAdapter = Adapter
MilkyBot = Bot
MilkyEvent = Event
MilkyMessage = Message
MilkyMessageSegment = MessageSegment
