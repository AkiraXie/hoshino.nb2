"""OneBot v11 类型 — Message, MessageSegment, Bot, Event 等"""

from nonebot.adapters.onebot.v11 import Adapter as Adapter
from nonebot.adapters.onebot.v11 import Bot as Bot
from nonebot.adapters.onebot.v11 import Event as Event
from nonebot.adapters.onebot.v11.event import (
    GroupMessageEvent as GroupMessageEvent,
)
from nonebot.adapters.onebot.v11.event import (
    MessageEvent as MessageEvent,
)
from nonebot.adapters.onebot.v11.event import (
    NoticeEvent as NoticeEvent,
)
from nonebot.adapters.onebot.v11.event import (
    PrivateMessageEvent as PrivateMessageEvent,
)
from nonebot.adapters.onebot.v11.message import Message as Message
from nonebot.adapters.onebot.v11.message import MessageSegment as MessageSegment
from nonebot.adapters.onebot.v11.utils import escape as escape

# 带 OneBotV11 前缀的别名 — 方便模块层显式声明 OB11 依赖
OneBotV11Adapter = Adapter
OneBotV11Bot = Bot
OneBotV11Event = Event
OneBotV11Message = Message
OneBotV11MessageSegment = MessageSegment
