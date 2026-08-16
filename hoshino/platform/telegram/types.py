"""Telegram adapter types."""

from nonebot.adapters.telegram import Adapter as Adapter
from nonebot.adapters.telegram import Bot as Bot
from nonebot.adapters.telegram import Event as Event
from nonebot.adapters.telegram import Message as Message
from nonebot.adapters.telegram import MessageSegment as MessageSegment
from nonebot.adapters.telegram.event import (
    ChannelPostEvent as ChannelPostEvent,
)
from nonebot.adapters.telegram.event import (
    EditedMessageEvent as EditedMessageEvent,
)
from nonebot.adapters.telegram.event import (
    GroupMessageEvent as GroupMessageEvent,
)
from nonebot.adapters.telegram.event import (
    MessageEvent as MessageEvent,
)
from nonebot.adapters.telegram.event import (
    NoticeEvent as NoticeEvent,
)
from nonebot.adapters.telegram.event import (
    PrivateMessageEvent as PrivateMessageEvent,
)
from nonebot.adapters.telegram.event import (
    RequestEvent as RequestEvent,
)

from hoshino.platform.telegram.events import (
    MessageReactionEvent as MessageReactionEvent,
)

TelegramAdapter = Adapter
TelegramBot = Bot
TelegramEvent = Event
TelegramMessage = Message
TelegramMessageSegment = MessageSegment
