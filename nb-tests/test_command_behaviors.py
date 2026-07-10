"""Cross-adapter command behavior tests for service management and Weibo."""

from dataclasses import dataclass, field
from typing import Any

import pytest
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
from nonebot_plugin_alconna import UniMessage


def _ob11_group_message(text: str) -> tuple[OB11Bot, OB11GroupMessageEvent]:
    adapter = OB11Adapter(get_driver())
    bot = OB11Bot(adapter, self_id="10000")
    message = OB11Message(OB11MessageSegment.text(text))
    event = OB11GroupMessageEvent(
        time=1,
        self_id=10000,
        post_type="message",
        sub_type="normal",
        user_id=42,
        message_type="group",
        message_id=8,
        message=message,
        original_message=message,
        raw_message=text,
        font=0,
        sender={"user_id": 42, "nickname": "Alice", "role": "admin"},
        group_id=123456,
        to_me=True,
    )
    return bot, event


def _telegram_group_message(text: str) -> tuple[TelegramBot, TelegramMessageEvent]:
    adapter = TelegramAdapter(get_driver())
    bot = TelegramBot(
        adapter,
        self_id="10000",
        config=TelegramBotConfig(token="10000:test"),
    )
    event = TelegramMessageEvent.parse_event(
        {
            "message_id": 8,
            "date": 1,
            "chat": {"id": -100123456, "type": "supergroup", "title": "test group"},
            "from": {"id": 42, "is_bot": False, "first_name": "Alice"},
            "text": text,
        }
    )
    event._tome = True
    return bot, event


@dataclass
class FakeService:
    scopes: dict[str, set[str]] = field(
        default_factory=lambda: {"enable": set(), "disable": set()}
    )

    async def manage_perm(self, bot, event) -> bool:
        return True

    def set_enable(self, scope: str) -> None:
        self.scopes["enable"].add(scope)

    def set_disable(self, scope: str) -> None:
        self.scopes["disable"].add(scope)


@pytest.mark.usefixtures("_nonebot_bootstrap")
@pytest.mark.parametrize(
    ("factory", "scope"),
    (
        (_ob11_group_message, "ob11:123456"),
        (_telegram_group_message, "telegram:-100123456"),
    ),
)
@pytest.mark.parametrize(
    ("action", "scope_bucket"),
    (("开启", "enable"), ("关闭", "disable")),
)
async def test_service_switch_updates_adapter_scope(
    monkeypatch: pytest.MonkeyPatch,
    factory,
    scope: str,
    action: str,
    scope_bucket: str,
):
    # Imported after the shared fixture initializes NoneBot and all matchers.
    from hoshino.base import service_manage
    from hoshino.core.service import Service

    fake_service = FakeService()
    monkeypatch.setattr(
        Service,
        "get_loaded_services",
        staticmethod(lambda: {"dice": fake_service}),
    )
    bot, event = factory(f"{action} dice")

    reply = await service_manage._switch_services(
        bot,
        event,
        ("dice",),
        UniMessage(),
        action=action,
        all_services=False,
    )

    assert reply == f"已{action}服务: dice"
    assert fake_service.scopes[scope_bucket] == {scope}


@pytest.mark.usefixtures("_nonebot_bootstrap")
@pytest.mark.parametrize("factory", (_ob11_group_message, _telegram_group_message))
async def test_weibo_list_empty_group_responds(
    monkeypatch: pytest.MonkeyPatch,
    factory,
):
    # Imported after the shared fixture initializes NoneBot and all matchers.
    from hoshino.modules.information import weibo
    from hoshino.platform import get_group_id

    sent: list[str] = []

    async def capture_send(message: UniMessage, *args: Any, **kwargs: Any):
        sent.append(message.extract_plain_text())

    monkeypatch.setattr(weibo, "list_group_subscriptions", lambda group_id: [])
    monkeypatch.setattr(UniMessage, "send", capture_send)

    _, event = factory("lswb")
    await weibo.list_subscriptions(get_group_id(event))

    assert sent == ["本群没有订阅微博用户"]
