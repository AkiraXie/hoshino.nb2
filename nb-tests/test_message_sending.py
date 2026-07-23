"""Cross-adapter outgoing message and constructed-forward coverage."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from nonebot.adapters.milky import Bot as MilkyBot
from nonebot.adapters.milky.model.api import MessageResponse
from nonebot.adapters.onebot.v11 import Bot as OB11Bot
from nonebot.adapters.onebot.v11 import Message as OB11Message
from nonebot.adapters.onebot.v11 import MessageSegment as OB11MessageSegment
from nonebot.adapters.telegram import Bot as TelegramBot
from nonebot_plugin_alconna.uniseg import UniMessage
from adapter_events import (
    ob11_group_message as _ob11_group_message,
    telegram_group_message as _telegram_group_message,
)
from test_milky_adapter import _milky_group_message


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_legacy_ob11_image_sends_through_milky_exporter(
    monkeypatch: pytest.MonkeyPatch,
):
    from hoshino.platform import send_to_event

    sent: list[tuple[int, Any]] = []

    async def fake_send_group_message(self, *, group_id: int, message):
        sent.append((group_id, message))
        return MessageResponse(message_seq=8, time=1)

    monkeypatch.setattr(MilkyBot, "send_group_message", fake_send_group_message)
    bot, event = _milky_group_message("ignored", to_me=False)

    await send_to_event(
        bot,
        event,
        OB11MessageSegment.image("https://example.com/image.jpg"),
    )

    assert sent[0][0] == 123456
    assert sent[0][1][0].type == "image"
    assert sent[0][1][0].data["uri"] == "https://example.com/image.jpg"


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_call_header_and_at_sender_are_consumed_before_milky_api(
    monkeypatch: pytest.MonkeyPatch,
):
    from hoshino.platform import send_to_event

    sent: list[Any] = []

    async def fake_send_group_message(self, *, group_id: int, message):
        assert group_id == 123456
        sent.append(message)
        return MessageResponse(message_seq=8, time=1)

    monkeypatch.setattr(MilkyBot, "send_group_message", fake_send_group_message)
    bot, event = _milky_group_message("ignored", to_me=False)

    await send_to_event(
        bot,
        event,
        "hello",
        at_sender=True,
        call_header=True,
    )

    assert [segment.type for segment in sent[0]] == ["text", "mention", "text"]
    assert sent[0][0].data["text"] == ">Alice member\n"
    assert sent[0][1].data["user_id"] == 42
    assert sent[0][2].data["text"] == " hello"


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_call_header_is_consumed_before_telegram_api(
    monkeypatch: pytest.MonkeyPatch,
):
    from hoshino.platform import message as platform_message

    sent: list[Any] = []

    async def fake_send(self, event, message, reply_markup=None):
        sent.append(message)
        return object()

    async def fake_get_session(bot, event):
        return SimpleNamespace(
            member=SimpleNamespace(nick="Alice"),
            user=SimpleNamespace(nick=None, name="Alice"),
        )

    monkeypatch.setattr(TelegramBot, "send", fake_send)
    monkeypatch.setattr(platform_message, "get_session", fake_get_session)
    bot, event = _telegram_group_message("ignored", to_me=False)

    await platform_message.send_to_event(bot, event, "hello", call_header=True)

    assert sent[0].extract_plain_text() == ">Alice\nhello"


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_call_header_lookup_failure_does_not_block_message(
    monkeypatch: pytest.MonkeyPatch,
):
    from hoshino.platform import message as platform_message

    sent: list[Any] = []

    async def fake_send_group_message(self, *, group_id: int, message):
        sent.append(message)
        return MessageResponse(message_seq=8, time=1)

    async def failing_get_session(bot, event):
        raise RuntimeError("profile lookup failed")

    monkeypatch.setattr(MilkyBot, "send_group_message", fake_send_group_message)
    monkeypatch.setattr(platform_message, "get_session", failing_get_session)
    bot, event = _milky_group_message("ignored", to_me=False)

    await platform_message.send_to_event(bot, event, "hello", call_header=True)

    assert sent[0].extract_plain_text() == "hello"


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_milky_constructed_forward_uses_native_forward_segment(
    monkeypatch: pytest.MonkeyPatch,
):
    from hoshino.platform import send_group_forward

    sent: list[Any] = []

    async def fake_send_group_message(self, *, group_id: int, message):
        assert group_id == 123456
        sent.append(message)
        return MessageResponse(message_seq=8, time=1)

    monkeypatch.setattr(MilkyBot, "send_group_message", fake_send_group_message)
    bot, _ = _milky_group_message("ignored", to_me=False)

    receipts = await send_group_forward(
        bot,
        123456,
        [
            "first",
            UniMessage.image(url="https://example.com/image.jpg"),
        ],
        user_id=bot.self_id,
        nickname="Hoshino",
        sequential_delay=0,
    )

    assert len(receipts) == 1
    assert len(sent[0]) == 1
    forward = sent[0][0]
    assert forward.type == "forward"
    nodes = forward.data["messages"]
    assert [node.sender_name for node in nodes] == ["Hoshino", "Hoshino"]
    assert nodes[0].segments.extract_plain_text() == "first"
    assert nodes[1].segments[0].data["uri"] == "https://example.com/image.jpg"


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_milky_private_constructed_forward_uses_native_forward_segment(
    monkeypatch: pytest.MonkeyPatch,
):
    from hoshino.platform import send_private_forward

    sent: list[Any] = []

    async def fake_send_private_message(self, *, user_id: int, message):
        assert user_id == 42
        sent.append(message)
        return MessageResponse(message_seq=8, time=1)

    monkeypatch.setattr(MilkyBot, "send_private_message", fake_send_private_message)
    bot, _ = _milky_group_message("ignored", to_me=False)

    receipts = await send_private_forward(
        bot,
        42,
        ["private node"],
        node_user_id=bot.self_id,
        nickname="Hoshino",
        sequential_delay=0,
    )

    assert len(receipts) == 1
    assert sent[0][0].type == "forward"
    assert (
        sent[0][0].data["messages"][0].segments.extract_plain_text() == "private node"
    )


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_milky_forward_accepts_legacy_ob11_custom_nodes(
    monkeypatch: pytest.MonkeyPatch,
):
    from hoshino.platform import send_group_forward

    sent: list[Any] = []

    async def fake_send_group_message(self, *, group_id: int, message):
        sent.append(message)
        return MessageResponse(message_seq=8, time=1)

    monkeypatch.setattr(MilkyBot, "send_group_message", fake_send_group_message)
    bot, _ = _milky_group_message("ignored", to_me=False)
    legacy_nodes = OB11Message(
        [
            OB11MessageSegment.node_custom(
                user_id=10000,
                nickname="Legacy",
                content=OB11Message("legacy content"),
            )
        ]
    )

    await send_group_forward(
        bot,
        123456,
        legacy_nodes,
        sequential_delay=0,
    )

    node = sent[0][0].data["messages"][0]
    assert node.sender_name == "Legacy"
    assert node.segments.extract_plain_text() == "legacy content"


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_ob11_constructed_forward_preserves_native_api(
    monkeypatch: pytest.MonkeyPatch,
):
    from hoshino.platform import send_group_forward

    calls: list[tuple[str, dict[str, Any]]] = []

    async def fake_call_api(self, api: str, **data: Any):
        calls.append((api, data))
        return {"message_id": 8}

    monkeypatch.setattr(OB11Bot, "call_api", fake_call_api)
    bot, _ = _ob11_group_message("ignored", to_me=False)

    receipts = await send_group_forward(
        bot,
        123456,
        ["first", UniMessage.text("second")],
        user_id=bot.self_id,
        nickname="Hoshino",
        sequential_delay=0,
    )

    assert len(receipts) == 1
    assert calls[0][0] == "send_group_forward_msg"
    assert calls[0][1]["group_id"] == 123456
    assert [segment.type for segment in calls[0][1]["messages"]] == [
        "node",
        "node",
    ]


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_telegram_constructed_forward_falls_back_to_sequential_messages(
    monkeypatch: pytest.MonkeyPatch,
):
    from hoshino.platform import send_group_forward

    sent: list[tuple[str, Any]] = []

    async def fake_send_to(self, chat_id, message, **kwargs):
        sent.append((str(chat_id), message))
        return object()

    monkeypatch.setattr(TelegramBot, "send_to", fake_send_to)
    bot, _ = _telegram_group_message("ignored", to_me=False)

    receipts = await send_group_forward(
        bot,
        -100123456,
        ["first", UniMessage.text("second")],
        user_id=bot.self_id,
        nickname="Hoshino",
        sequential_delay=0,
    )

    assert len(receipts) == 2
    assert [chat_id for chat_id, _ in sent] == ["-100123456", "-100123456"]
    assert [message.extract_plain_text() for _, message in sent] == [
        "first",
        "second",
    ]
