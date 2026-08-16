from nonebot import get_driver
from nonebot.adapters.onebot.v11 import Adapter as OB11Adapter
from nonebot.adapters.onebot.v11 import Bot as OB11Bot
from nonebot.adapters.onebot.v11 import GroupMessageEvent as OB11GroupMessageEvent
from nonebot.adapters.onebot.v11 import Message as OB11Message
from nonebot.adapters.onebot.v11 import MessageSegment as OB11MessageSegment
from nonebot.adapters.telegram import Adapter as TelegramAdapter
from nonebot.adapters.telegram import Bot as TelegramBot
from nonebot.adapters.telegram.config import BotConfig as TelegramBotConfig
from nonebot.adapters.telegram.event import MessageEvent as TelegramMessageEvent


def ob11_group_message(
    text: str, *, to_me: bool, user_id: int = 42, reply: dict | None = None
) -> tuple[OB11Bot, OB11GroupMessageEvent]:
    adapter = OB11Adapter(get_driver())
    bot = OB11Bot(adapter, self_id="10000")
    message = OB11Message(OB11MessageSegment.text(text))
    data = {
        "time": 1,
        "self_id": 10000,
        "post_type": "message",
        "sub_type": "normal",
        "user_id": user_id,
        "message_type": "group",
        "message_id": 7,
        "message": message,
        "original_message": message,
        "raw_message": text,
        "font": 0,
        "sender": {"user_id": user_id, "nickname": "Alice", "role": "admin"},
        "group_id": 123456,
        "to_me": to_me,
    }
    if reply is not None:
        data["reply"] = reply
    event = OB11GroupMessageEvent(**data)
    return bot, event


def telegram_group_message(
    text: str, *, to_me: bool, user_id: int = 42
) -> tuple[TelegramBot, TelegramMessageEvent]:
    adapter = TelegramAdapter(get_driver())
    bot = TelegramBot(
        adapter,
        self_id="10000",
        config=TelegramBotConfig(token="10000:test"),
    )
    event = TelegramMessageEvent.parse_event(
        {
            "message_id": 7,
            "date": 1,
            "chat": {"id": -100123456, "type": "supergroup", "title": "test group"},
            "from": {"id": user_id, "is_bot": False, "first_name": "Alice"},
            "text": text,
        }
    )
    event._tome = to_me
    return bot, event
