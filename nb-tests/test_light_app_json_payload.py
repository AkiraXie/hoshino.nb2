"""Cross-adapter mini-program JSON dependency coverage."""

from __future__ import annotations

import json
from typing import Any

import pytest
from nonebot import get_adapters
from nonebot.adapters.milky import Adapter as MilkyAdapter
from nonebot.adapters.onebot.v11 import Message as OB11Message
from nonebot.adapters.onebot.v11 import MessageSegment as OB11MessageSegment

from hoshino.platform.depends import get_light_app_json_payload
from test_command_adapters import _ob11_group_message


def _mini_program_payload(url: str) -> dict[str, Any]:
    return {"meta": {"detail_1": {"qqdocurl": url}}}


def _milky_light_app_event(payload: dict[str, Any]):
    adapter = get_adapters()[MilkyAdapter.get_name()]
    return adapter.json_to_event(
        {
            "event_type": "message_receive",
            "time": 1,
            "self_id": 10000,
            "data": {
                "message_scene": "group",
                "peer_id": 123456,
                "message_seq": 1,
                "sender_id": 42,
                "time": 1,
                "segments": [
                    {
                        "type": "light_app",
                        "data": {"json_payload": json.dumps(payload)},
                    }
                ],
                "group": {
                    "group_id": 123456,
                    "group_name": "test group",
                    "member_count": 2,
                    "max_member_count": 100,
                },
                "group_member": {
                    "user_id": 42,
                    "nickname": "TestUser",
                    "sex": "unknown",
                    "group_id": 123456,
                    "card": "TestCard",
                    "title": "",
                    "level": 1,
                    "role": "member",
                    "join_time": 1,
                    "last_sent_time": 1,
                },
            },
        }
    )


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_light_app_json_payload_reads_legacy_ob11_json_segment():
    payload = _mini_program_payload("https://b23.tv/legacy")
    _bot, event = _ob11_group_message("", to_me=False)
    message = OB11Message(OB11MessageSegment.json(json.dumps(payload)))
    event.message = message
    event.original_message = message

    assert get_light_app_json_payload(event) == payload


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_light_app_json_payload_reads_milky_light_app_segment():
    from hoshino.modules.information.resolve import check_json_or_text

    payload = _mini_program_payload("https://b23.tv/lightapp")
    event = _milky_light_app_event(payload)
    resolved_payload = get_light_app_json_payload(event)
    state = {}

    assert resolved_payload == payload
    assert await check_json_or_text(event, state, resolved_payload)
    assert state["__url_name"] == "b23"
    assert state["__url"] == "https://b23.tv/lightapp"


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_light_app_json_payload_ignores_plain_text():
    _bot, event = _ob11_group_message("https://b23.tv/plain", to_me=False)

    assert get_light_app_json_payload(event) is None
