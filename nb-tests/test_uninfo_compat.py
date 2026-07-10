from collections.abc import Iterator
from contextlib import contextmanager

from exceptiongroup import ExceptionGroup
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
from nonebot.matcher import Matcher
from nonebot_plugin_uninfo import (
    Member,
    Role,
    Scene,
    SceneType,
    Session,
    SupportAdapter,
    SupportScope,
    Uninfo,
    User,
)
from nonebot_plugin_uninfo.adapters import INFO_FETCHER_MAPPING, alter_get_fetcher
from nonebug import App
import pytest

from hoshino.platform.depends import GroupID, GroupMemberName, SenderID
from hoshino.platform.permission import GROUP_ADMIN, GROUP_OWNER


async def session_values(
    group_id: int | None = GroupID(),
    sender_id: int | None = SenderID(),
    member_name: str = GroupMemberName(),
) -> tuple[int | None, int | None, str]:
    return group_id, sender_id, member_name


async def uninfo_adapter(session: Uninfo) -> str:
    return str(session.adapter)


@contextmanager
def cached_session(bot, event, session: Session) -> Iterator[None]:
    adapter_name = bot.adapter.get_name()
    fetcher = INFO_FETCHER_MAPPING.get(adapter_name) or alter_get_fetcher(adapter_name)
    assert fetcher is not None
    session_id = fetcher.get_session_id(event)
    fetcher.session_cache[session_id] = session
    try:
        yield
    finally:
        fetcher.session_cache.pop(session_id, None)


def make_session(
    *,
    adapter: SupportAdapter,
    scope: SupportScope,
    scene_id: str,
    user_id: str,
) -> Session:
    user = User(id=user_id, name="alice", nick="Alice")
    return Session(
        self_id="10000",
        adapter=adapter,
        scope=scope,
        scene=Scene(id=scene_id, type=SceneType.GROUP, name="test group"),
        user=user,
        member=Member(
            user=user,
            nick="Alice member",
            role=Role(id="ADMINISTRATOR", level=10, name="admin"),
        ),
    )


async def test_ob11_uninfo_dependencies(app: App):
    async with app.test_dependent(
        session_values,
        allow_types=Matcher.HANDLER_PARAM_TYPES,
    ) as ctx:
        adapter = OB11Adapter(get_driver())
        bot = OB11Bot(adapter, self_id="10000")
        event = OB11GroupMessageEvent(
            time=1,
            self_id=10000,
            post_type="message",
            sub_type="normal",
            user_id=42,
            message_type="group",
            message_id=7,
            message=OB11Message(OB11MessageSegment.text("hello")),
            original_message=OB11Message(OB11MessageSegment.text("hello")),
            raw_message="hello",
            font=0,
            sender={"user_id": 42, "nickname": "Alice", "role": "admin"},
            group_id=123456,
        )
        session = make_session(
            adapter=SupportAdapter.onebot11,
            scope=SupportScope.qq_client,
            scene_id="123456",
            user_id="42",
        )
        ctx.stack.enter_context(cached_session(bot, event, session))
        assert await GROUP_ADMIN(bot, event)
        assert not await GROUP_OWNER(bot, event)
        ctx.pass_params(bot=bot, event=event)
        ctx.should_return((123456, 42, "Alice member"))


async def test_telegram_uninfo_dependencies(app: App):
    async with app.test_dependent(
        session_values,
        allow_types=Matcher.HANDLER_PARAM_TYPES,
    ) as ctx:
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
                "chat": {
                    "id": -100123456,
                    "type": "supergroup",
                    "title": "test group",
                },
                "from": {
                    "id": 42,
                    "is_bot": False,
                    "first_name": "Alice",
                },
                "text": "hello",
            }
        )
        session = make_session(
            adapter=SupportAdapter.telegram,
            scope=SupportScope.telegram,
            scene_id="-100123456",
            user_id="42",
        )
        ctx.stack.enter_context(cached_session(bot, event, session))
        assert await GROUP_ADMIN(bot, event)
        assert not await GROUP_OWNER(bot, event)
        ctx.pass_params(bot=bot, event=event)
        ctx.should_return((-100123456, 42, "Alice member"))


@pytest.mark.xfail(
    raises=(TypeError, ExceptionGroup),
    reason="upstream: nonebot-plugin-uninfo 0.6.10 Session._validate incompatible with Pydantic >=2.12",
    strict=False,
)
async def test_upstream_uninfo_alias_on_pydantic_212(app: App):
    async with app.test_dependent(
        uninfo_adapter,
        allow_types=Matcher.HANDLER_PARAM_TYPES,
    ) as ctx:
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
                "chat": {
                    "id": -100123456,
                    "type": "supergroup",
                    "title": "test group",
                },
                "from": {
                    "id": 42,
                    "is_bot": False,
                    "first_name": "Alice",
                },
                "text": "hello",
            }
        )
        session = make_session(
            adapter=SupportAdapter.telegram,
            scope=SupportScope.telegram,
            scene_id="-100123456",
            user_id="42",
        )
        ctx.stack.enter_context(cached_session(bot, event, session))
        ctx.pass_params(bot=bot, event=event)
        ctx.should_return("Telegram")
