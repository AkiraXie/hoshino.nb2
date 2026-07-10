"""Telegram adapter types."""

from nonebot.adapters.telegram import Adapter as Adapter
from nonebot.adapters.telegram import Bot as Bot
from nonebot.adapters.telegram import Event as Event
from nonebot.adapters.telegram import Message as Message
from nonebot.adapters.telegram import MessageSegment as MessageSegment
from nonebot.adapters.telegram.event import (
    ChannelPostEvent as ChannelPostEvent,
    EditedMessageEvent as EditedMessageEvent,
    GroupMessageEvent as GroupMessageEvent,
    MessageEvent as MessageEvent,
    NoticeEvent as NoticeEvent,
    PrivateMessageEvent as PrivateMessageEvent,
    RequestEvent as RequestEvent,
)

TelegramAdapter = Adapter
TelegramBot = Bot
TelegramEvent = Event
TelegramMessage = Message
TelegramMessageSegment = MessageSegment

