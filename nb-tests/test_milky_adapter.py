"""Focused Milky integration and cross-adapter reaction coverage."""

from __future__ import annotations

from typing import Any

import pytest
from arclet.alconna import command_manager
from nonebot import get_adapters
from nonebot.adapters.milky import Adapter as MilkyAdapter
from nonebot.adapters.milky import Bot as MilkyBot
from nonebot.adapters.milky.config import ClientInfo
from nonebot.adapters.milky.event import GroupMessageEvent as MilkyGroupMessageEvent
from nonebot.adapters.milky.event import (
    GroupMessageReactionEvent as MilkyReactionEvent,
)
from nonebot.adapters.milky.model.api import MessageResponse
from nonebot.adapters.milky.model.common import Group as MilkyGroup
from nonebot.adapters.milky.model.common import Member as MilkyMember
from nonebot.adapters.milky.model.message import IncomingMessage
from nonebot.adapters.onebot.v11 import Bot as OB11Bot
from nonebot.matcher import Matcher, current_bot, matchers
from nonebot.rule import TrieRule
from nonebot_plugin_alconna.uniseg import UniMessage
from nonebug import App


def _milky_group_message(
    text: str,
    *,
    to_me: bool,
    user_id: int = 42,
) -> tuple[MilkyBot, MilkyGroupMessageEvent]:
    adapter = get_adapters()[MilkyAdapter.get_name()]
    bot = MilkyBot(adapter, self_id="10000", info=ClientInfo())
    event = adapter.json_to_event(
        {
            "event_type": "message_receive",
            "time": 1,
            "self_id": 10000,
            "data": {
                "message_scene": "group",
                "peer_id": 123456,
                "message_seq": 7,
                "sender_id": user_id,
                "time": 1,
                "segments": [{"type": "text", "data": {"text": text}}],
                "group": {
                    "group_id": 123456,
                    "group_name": "test group",
                    "member_count": 2,
                    "max_member_count": 100,
                },
                "group_member": {
                    "user_id": user_id,
                    "nickname": "Alice",
                    "sex": "unknown",
                    "group_id": 123456,
                    "card": "Alice member",
                    "title": "",
                    "level": 1,
                    "role": "admin",
                    "join_time": 1,
                    "last_sent_time": 1,
                },
            },
        }
    )
    assert isinstance(event, MilkyGroupMessageEvent)
    event.to_me = to_me
    return bot, event


def _milky_reaction(
    face_id: str = "66",
    *,
    is_add: bool = True,
    reaction_type: str = "face",
) -> MilkyReactionEvent:
    event = MilkyAdapter.json_to_event(
        {
            "event_type": "group_message_reaction",
            "time": 1,
            "self_id": 10000,
            "data": {
                "group_id": 123456,
                "user_id": 42,
                "message_seq": 7,
                "face_id": face_id,
                "reaction_type": reaction_type,
                "is_add": is_add,
            },
        }
    )
    assert isinstance(event, MilkyReactionEvent)
    return event


def _ob11_reaction(face_id: str = "66"):
    from hoshino.platform.ob11.events import GroupReactionEvent

    return GroupReactionEvent(
        time=1,
        self_id=10000,
        post_type="notice",
        notice_type="reaction",
        sub_type="add",
        group_id=123456,
        message_id=7,
        operator_id=42,
        code=face_id,
        count=1,
    )


def _ob11_emoji_like(face_id: str = "66"):
    from hoshino.platform.ob11.events import GroupMsgEmojiLikeEvent

    return GroupMsgEmojiLikeEvent(
        time=1,
        self_id=10000,
        post_type="notice",
        notice_type="group_msg_emoji_like",
        group_id=123456,
        message_id=7,
        user_id=42,
        likes=[{"emoji_id": face_id, "count": 1}],
    )


def _matcher_for_handler(handler):
    for matcher_group in matchers.values():
        for matcher in matcher_group:
            if any(dependent.call is handler for dependent in matcher.handlers):
                return matcher
    raise AssertionError(
        f"No matcher registered for {handler.__module__}.{handler.__name__}"
    )


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_milky_event_accessors_and_native_command_rule():
    from hoshino.base.image import delete_img_cmd
    from hoshino.platform import (
        get_group_id,
        get_message_id,
        get_plaintext,
        get_user_id,
        is_group_event,
        is_message_event,
        is_private_event,
    )

    bot, event = _milky_group_message("删图 example.jpg", to_me=True)
    assert get_group_id(event) == 123456
    assert get_user_id(event) == 42
    assert get_message_id(event) == 7
    assert get_plaintext(event) == "删图 example.jpg"
    assert is_message_event(event)
    assert is_group_event(event)
    assert not is_private_event(event)

    matcher = _matcher_for_handler(delete_img_cmd)
    state: dict[str, Any] = {}
    TrieRule.get_value(bot, event, state)
    assert await matcher.rule(bot, event, state)


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_milky_alconna_commands_parse_without_adapter_branches():
    from hoshino.base.service_manage import lssv

    bot, event = _milky_group_message("lssv", to_me=True)
    assert await lssv.rule(bot, event, {})

    command = command_manager.get_command("微博订阅")
    assert command is not None
    bot, event = _milky_group_message("lswb", to_me=False)
    token = current_bot.set(bot)
    try:
        assert command.parse(event.get_message()).matched
    finally:
        current_bot.reset(token)


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_milky_uninfo_dependencies_and_permission(app: App):
    from hoshino.platform.depends import GroupID, GroupMemberName, SenderID
    from hoshino.platform.permission import GROUP_ADMIN, GROUP_OWNER

    async def session_values(
        group_id: int | None = GroupID(),
        sender_id: int | None = SenderID(),
        member_name: str = GroupMemberName(),
    ) -> tuple[int | None, int | None, str]:
        return group_id, sender_id, member_name

    bot, event = _milky_group_message("hello", to_me=False)
    assert await GROUP_ADMIN(bot, event)
    assert not await GROUP_OWNER(bot, event)

    async with app.test_dependent(
        session_values,
        allow_types=Matcher.HANDLER_PARAM_TYPES,
    ) as ctx:
        ctx.pass_params(bot=bot, event=event)
        ctx.should_return((123456, 42, "Alice member"))


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_milky_group_api_wrappers_return_common_dicts(
    monkeypatch: pytest.MonkeyPatch,
):
    from hoshino.platform import get_group_list, get_group_member_info

    async def fake_group_list(self, *, no_cache: bool = False):
        assert not no_cache
        return [
            MilkyGroup(
                group_id=123456,
                group_name="test group",
                member_count=2,
                max_member_count=100,
            )
        ]

    async def fake_group_member_info(
        self,
        *,
        group_id: int,
        user_id: int,
        no_cache: bool = False,
    ):
        assert (group_id, user_id, no_cache) == (123456, 42, True)
        return MilkyMember(
            user_id=42,
            nickname="Alice",
            sex="unknown",
            group_id=123456,
            card="Alice member",
            title="",
            level=1,
            role="admin",
            join_time=1,
            last_sent_time=1,
        )

    monkeypatch.setattr(MilkyBot, "get_group_list", fake_group_list)
    monkeypatch.setattr(MilkyBot, "get_group_member_info", fake_group_member_info)
    bot, _ = _milky_group_message("hello", to_me=False)

    groups = await get_group_list(bot)
    member = await get_group_member_info(bot, 123456, 42)
    assert groups[0]["group_id"] == 123456
    assert member["card"] == "Alice member"
    assert member["role"] == "admin"


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_unimessage_sends_to_milky_target(monkeypatch: pytest.MonkeyPatch):
    from hoshino.platform import group_target, send_to_target

    sent: list[tuple[int, Any]] = []

    async def fake_send_group_message(self, *, group_id: int, message):
        sent.append((group_id, message))
        return MessageResponse(message_seq=8, time=1)

    monkeypatch.setattr(MilkyBot, "send_group_message", fake_send_group_message)
    bot, _ = _milky_group_message("hello", to_me=False)

    await send_to_target(bot, group_target(123456), UniMessage.text("hello"))

    assert sent[0][0] == 123456
    assert sent[0][1].extract_plain_text() == "hello"


@pytest.mark.usefixtures("_nonebot_bootstrap")
@pytest.mark.parametrize(
    "event",
    (
        pytest.param(_ob11_reaction(), id="ob11-reaction"),
        pytest.param(_ob11_emoji_like(), id="ob11-emoji-like"),
        pytest.param(_milky_reaction(), id="milky-reaction"),
    ),
)
async def test_reaction_di_normalizes_ob11_and_milky(app: App, event):
    from hoshino.platform import Reaction, ReactionInfo

    async def reaction_value(
        reaction: ReactionInfo | None = Reaction(),
    ) -> ReactionInfo | None:
        return reaction

    if isinstance(event, MilkyReactionEvent):
        bot, _ = _milky_group_message("ignored", to_me=False)
    else:
        adapter = get_adapters()["OneBot V11"]
        bot = OB11Bot(adapter, self_id="10000")

    expected = ReactionInfo(
        face_id="66",
        is_add=True,
        message_id=7,
        group_id=123456,
        user_id=42,
        reaction_type=(
            "emoji" if event.__class__.__name__.endswith("EmojiLikeEvent") else "face"
        ),
    )
    async with app.test_dependent(
        reaction_value,
        allow_types=Matcher.HANDLER_PARAM_TYPES,
    ) as ctx:
        ctx.pass_params(bot=bot, event=event)
        ctx.should_return(expected)


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_reacted_message_di_fetches_milky_message(
    app: App,
    monkeypatch: pytest.MonkeyPatch,
):
    from hoshino.platform import ReactedMessage, RetrievedMessage

    async def reacted_message_value(
        message: RetrievedMessage | None = ReactedMessage(),
    ) -> tuple[str, bool, str | None] | None:
        if message is None:
            return None
        image = message.content[0]
        return message.sender_id, message.trusted_sender, getattr(image, "url", None)

    async def fake_get_message(
        self,
        *,
        message_scene: str,
        peer_id: int,
        message_seq: int,
    ) -> IncomingMessage:
        assert message_scene == "group"
        assert peer_id == 123456
        assert message_seq == 7
        return IncomingMessage.model_validate(
            {
                "message_scene": "group",
                "peer_id": peer_id,
                "message_seq": message_seq,
                "sender_id": 10000,
                "time": 1,
                "segments": [
                    {
                        "type": "image",
                        "data": {
                            "resource_id": "image-resource",
                            "temp_url": "https://example.com/image.jpg",
                            "width": 100,
                            "height": 100,
                            "sub_type": "normal",
                        },
                    }
                ],
            }
        )

    monkeypatch.setattr(MilkyBot, "get_message", fake_get_message)
    bot, _ = _milky_group_message("ignored", to_me=False)
    event = _milky_reaction()
    async with app.test_dependent(
        reacted_message_value,
        allow_types=Matcher.HANDLER_PARAM_TYPES,
    ) as ctx:
        ctx.pass_params(bot=bot, event=event)
        ctx.should_return(("10000", True, "https://example.com/image.jpg"))


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_milky_reaction_reaches_image_matcher_rule(
    monkeypatch: pytest.MonkeyPatch,
):
    from hoshino.base.image import svimg_notice
    from hoshino.util.media import SUPERUSER_IMAGE_LIST

    async def fake_get_message(
        self,
        *,
        message_scene: str,
        peer_id: int,
        message_seq: int,
    ) -> IncomingMessage:
        return IncomingMessage.model_validate(
            {
                "message_scene": message_scene,
                "peer_id": peer_id,
                "message_seq": message_seq,
                "sender_id": 10000,
                "time": 1,
                "segments": [
                    {
                        "type": "image",
                        "data": {
                            "resource_id": "image-resource",
                            "temp_url": "https://example.com/image.jpg",
                            "width": 100,
                            "height": 100,
                            "sub_type": "normal",
                        },
                    }
                ],
            }
        )

    monkeypatch.setattr(MilkyBot, "get_message", fake_get_message)
    bot, _ = _milky_group_message("ignored", to_me=False)
    event = _milky_reaction()
    state: dict[str, Any] = {}

    assert await svimg_notice.rule(bot, event, state)
    assert state[SUPERUSER_IMAGE_LIST][0].url == "https://example.com/image.jpg"


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_reacted_message_di_preserves_ob11_fetch(
    app: App,
    monkeypatch: pytest.MonkeyPatch,
):
    from hoshino.platform import ReactedMessage, RetrievedMessage

    async def reacted_message_value(
        message: RetrievedMessage | None = ReactedMessage(),
    ) -> tuple[str, bool, str | None] | None:
        if message is None:
            return None
        image = message.content[0]
        return message.sender_id, message.trusted_sender, getattr(image, "url", None)

    async def fake_call_api(self, api: str, **data: Any):
        assert api == "get_msg"
        assert data == {"message_id": 7}
        return {
            "sender": {"user_id": 10000},
            "message": [
                {
                    "type": "image",
                    "data": {
                        "file": "image-resource",
                        "url": "https://example.com/image.jpg",
                    },
                }
            ],
        }

    monkeypatch.setattr(OB11Bot, "call_api", fake_call_api)
    adapter = get_adapters()["OneBot V11"]
    bot = OB11Bot(adapter, self_id="10000")
    event = _ob11_reaction()
    async with app.test_dependent(
        reacted_message_value,
        allow_types=Matcher.HANDLER_PARAM_TYPES,
    ) as ctx:
        ctx.pass_params(bot=bot, event=event)
        ctx.should_return(("10000", True, "https://example.com/image.jpg"))


@pytest.mark.usefixtures("_nonebot_bootstrap")
@pytest.mark.parametrize(
    "event",
    (
        pytest.param(_ob11_reaction(), id="ob11-reaction"),
        pytest.param(_ob11_emoji_like(), id="ob11-emoji-like"),
        pytest.param(_milky_reaction(), id="milky-reaction"),
    ),
)
async def test_image_reaction_business_rule_is_adapter_neutral(event):
    from hoshino.base.image import reaction_img_rule
    from hoshino.platform import RetrievedMessage, get_reaction_info
    from hoshino.util.media import SUPERUSER_IMAGE_LIST

    reaction = get_reaction_info(event)
    assert reaction is not None
    message = RetrievedMessage(
        sender_id="10000",
        content=UniMessage.image(url="https://example.com/image.jpg"),
        trusted_sender=True,
    )
    state: dict[str, Any] = {}
    assert await reaction_img_rule(
        state,
        reaction=reaction,
        reacted_message=message,
    )
    assert state[SUPERUSER_IMAGE_LIST][0].url == "https://example.com/image.jpg"


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_weibo_reaction_rule_uses_common_reaction_object():
    from hoshino.modules.information.weibo.resolve import reaction_weibo_rule
    from hoshino.platform import ReactionInfo, RetrievedMessage

    reaction = ReactionInfo(
        face_id="319",
        is_add=True,
        message_id=7,
        group_id=123456,
        user_id=42,
        reaction_type="emoji",
    )
    message = RetrievedMessage(
        sender_id="10000",
        content=UniMessage.text("https://weibo.com/123/abc"),
        trusted_sender=True,
    )
    state: dict[str, Any] = {}
    assert await reaction_weibo_rule(
        state,
        reaction=reaction,
        reacted_message=message,
    )
    assert state["__weibo_url"] == "https://weibo.com/123/abc"
