"""Cross-adapter matcher rule coverage for representative commands."""

import pytest
from arclet.alconna import command_manager
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
from nonebot.matcher import current_bot


def _ob11_group_message(
    text: str, *, to_me: bool, user_id: int = 42
) -> tuple[OB11Bot, OB11GroupMessageEvent]:
    adapter = OB11Adapter(get_driver())
    bot = OB11Bot(adapter, self_id="10000")
    message = OB11Message(OB11MessageSegment.text(text))
    event = OB11GroupMessageEvent(
        time=1,
        self_id=10000,
        post_type="message",
        sub_type="normal",
        user_id=user_id,
        message_type="group",
        message_id=7,
        message=message,
        original_message=message,
        raw_message=text,
        font=0,
        sender={"user_id": user_id, "nickname": "Alice", "role": "admin"},
        group_id=123456,
        to_me=to_me,
    )
    return bot, event


def _telegram_group_message(
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


@pytest.mark.usefixtures("_nonebot_bootstrap")
@pytest.mark.parametrize("factory", (_ob11_group_message, _telegram_group_message))
async def test_lssv_matcher_rule_accepts_group_messages_on_both_adapters(factory):
    """The service list command reaches its matcher rule on both supported adapters."""
    from hoshino.base.service_manage import lssv

    bot, event = factory("lssv", to_me=True)
    assert await lssv.rule(bot, event, {})


@pytest.mark.usefixtures("_nonebot_bootstrap")
@pytest.mark.parametrize("factory", (_ob11_group_message, _telegram_group_message))
async def test_chooseone_regex_rule_accepts_group_messages_on_both_adapters(factory):
    """Natural-language choices reach the native regex rule on both adapters."""
    from hoshino.modules.interactive.chooseone import co

    bot, event = factory("choose apple or orange", to_me=False)

    assert await co.matcher.rule(bot, event, {})


@pytest.mark.usefixtures("_nonebot_bootstrap")
@pytest.mark.parametrize("factory", (_ob11_group_message, _telegram_group_message))
def test_lswb_accepts_adapter_messages_without_arguments(factory):
    """Legacy no-argument Weibo aliases parse from both adapter message types."""
    command = command_manager.get_command("微博订阅")
    assert command is not None

    bot, event = factory("lswb", to_me=False, user_id=43)
    token = current_bot.set(bot)
    try:
        assert command.parse(event.get_message()).matched
    finally:
        current_bot.reset(token)
