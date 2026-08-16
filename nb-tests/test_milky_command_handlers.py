"""Milky command handlers must resolve Alconna results before sending."""

from __future__ import annotations

import pytest
from nonebot.adapters.milky import Bot as MilkyBot
from nonebot.adapters.milky.model.api import MessageResponse

from _helpers import _milky_group_message


@pytest.mark.usefixtures("_nonebot_bootstrap")
@pytest.mark.parametrize("text", ("吃什么", "今天吃什么"))
async def test_foods_handler_sends_text_and_image_on_milky(
    monkeypatch: pytest.MonkeyPatch,
    text: str,
):
    from hoshino.modules.interactive import foods

    sent: list[tuple[int, object]] = []

    async def fake_send_group_message(self, *, group_id: int, message):
        sent.append((group_id, message))
        return MessageResponse(message_seq=8, time=1)

    monkeypatch.setattr(MilkyBot, "send_group_message", fake_send_group_message)
    monkeypatch.setattr(foods.sv, "check_enabled", lambda scope: True)
    bot, event = _milky_group_message(text, to_me=False)
    event.data.message_seq = 1000 if text == "吃什么" else 1001

    await bot.handle_event(event)

    assert len(sent) == 1
    group_id, message = sent[0]
    assert group_id == 123456
    assert [segment.type for segment in message] == ["text", "image"]
    assert "吃" in message.extract_plain_text()
