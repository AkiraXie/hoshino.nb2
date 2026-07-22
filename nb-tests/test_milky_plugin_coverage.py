"""Per-plugin Milky behavioral tests — handle_event() + HTTP assertions.

Each matcher-bearing plugin gets 1–2 real-entry cases following
``docs/milky-plugin-test-protocol.md``. Tests patch the registered Milky
adapter's ``call_http`` method to capture ``(action, params)`` records, and
stub handler-owned HTTP clients to prevent live outbound HTTP.

Uses the session-scoped ``_nonebot_bootstrap`` fixture from conftest.py.
"""

from __future__ import annotations

import sys
from types import SimpleNamespace
from typing import Any

import pytest
from nonebot import get_adapters
from nonebot.adapters.milky import Adapter as MilkyAdapter
from nonebot.adapters.milky import Bot as MilkyBot
from nonebot.adapters.milky.config import ClientInfo
from nonebot.adapters.milky.event import FriendMessageEvent as MilkyFriendMessageEvent
from nonebot.adapters.milky.event import GroupMessageEvent as MilkyGroupMessageEvent
from nonebot.adapters.milky.event import GroupMessageReactionEvent
from nonebot.adapters.milky.utils import clean_params
from PIL import Image as PILImage

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

_seq = 100000


def _next_seq() -> int:
    global _seq
    _seq += 1
    return _seq


def _loaded_module(name: str) -> Any:
    """Return a plugin module loaded by the session-scoped bootstrap fixture."""
    return sys.modules[name]


def _make_bot() -> MilkyBot:
    return MilkyBot(
        get_adapters()[MilkyAdapter.get_name()],
        self_id="10000",
        info=ClientInfo(),
    )


def _make_message(
    text: str,
    *,
    scene: str = "group",
    group_id: int = 123456,
    sender_id: int = 42,
    sender_role: str = "member",
    seq: int | None = None,
    segments: list[dict[str, Any]] | None = None,
) -> MilkyGroupMessageEvent | MilkyFriendMessageEvent:
    adapter = get_adapters()[MilkyAdapter.get_name()]
    seq = seq or _next_seq()
    if segments is None:
        segments = [{"type": "text", "data": {"text": text}}]
    event = adapter.json_to_event(
        {
            "event_type": "message_receive",
            "time": 1,
            "self_id": 10000,
            "data": {
                "message_scene": scene,
                "peer_id": group_id if scene == "group" else sender_id,
                "message_seq": seq,
                "sender_id": sender_id,
                "time": 1,
                "segments": segments,
                **(
                    {
                        "group": {
                            "group_id": group_id,
                            "group_name": "test group",
                            "member_count": 2,
                            "max_member_count": 100,
                        },
                        "group_member": {
                            "user_id": sender_id,
                            "nickname": "TestUser",
                            "sex": "unknown",
                            "group_id": group_id,
                            "card": "TestCard",
                            "title": "",
                            "level": 1,
                            "role": sender_role,
                            "join_time": 1,
                            "last_sent_time": 1,
                        },
                    }
                    if scene == "group"
                    else {
                        "friend": {
                            "user_id": sender_id,
                            "nickname": "TestUser",
                            "sex": "unknown",
                            "qid": "test-user",
                            "remark": "TestUser",
                            "category": {
                                "category_id": 1,
                                "category_name": "test",
                            },
                        }
                    }
                ),
            },
        }
    )
    assert isinstance(event, (MilkyFriendMessageEvent, MilkyGroupMessageEvent))
    return event


def _make_group_msg(text: str, **kwargs: Any) -> MilkyGroupMessageEvent:
    event = _make_message(text, scene="group", **kwargs)
    assert isinstance(event, MilkyGroupMessageEvent)
    return event


def _make_friend_msg(text: str, **kwargs: Any) -> MilkyFriendMessageEvent:
    event = _make_message(text, scene="friend", **kwargs)
    assert isinstance(event, MilkyFriendMessageEvent)
    return event


def _make_reaction_notice(
    *,
    message_seq: int = 7001,
    face_id: str = "319",
) -> GroupMessageReactionEvent:
    adapter = get_adapters()[MilkyAdapter.get_name()]
    event = adapter.json_to_event(
        {
            "event_type": "group_message_reaction",
            "time": 1,
            "self_id": 10000,
            "data": {
                "group_id": 123456,
                "user_id": _superuser_id(),
                "message_seq": message_seq,
                "face_id": face_id,
                "reaction_type": "face",
                "is_add": True,
            },
        }
    )
    assert isinstance(event, GroupMessageReactionEvent)
    return event


def _at_bot_msg(text: str, **kw) -> MilkyGroupMessageEvent:
    return _make_group_msg(
        "",
        segments=[
            {"type": "mention", "data": {"user_id": 10000}},
            {"type": "text", "data": {"text": text}},
        ],
        **kw,
    )


def _superuser_id() -> int:
    adapter = get_adapters()[MilkyAdapter.get_name()]
    return int(next(iter(adapter.config.superusers)))


def _stub_all_api(
    monkeypatch: pytest.MonkeyPatch,
    *,
    referenced_text: str = "stubbed",
    referenced_sender_id: int = 42,
    referenced_segments: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Capture the registered adapter's Milky HTTP boundary.

    Also stub ``hoshino.util.aiohttpx.post`` so handlers that perform
    outbound HTTP lookups do not open live connections.
    """

    calls: list[dict[str, Any]] = []
    if referenced_segments is None:
        referenced_segments = [{"type": "text", "data": {"text": referenced_text}}]

    async def _fake_call(
        self: MilkyAdapter,
        info: ClientInfo,
        action: str,
        params: dict | None = None,
    ) -> dict[str, Any]:
        p = clean_params(dict(params or {}))
        calls.append({"action": action, "params": p})
        if action in ("send_group_message", "send_private_message"):
            return {"message_seq": _next_seq(), "time": 1}
        if action == "get_group_member_info":
            return {
                "user_id": p.get("user_id", 0),
                "nickname": "TestUser",
                "card": "TestCard",
                "sex": "unknown",
                "role": "member",
                "join_time": 1,
            }
        if action == "get_group_list":
            return {
                "groups": [
                    {
                        "group_id": 123456,
                        "group_name": "test group",
                        "member_count": 2,
                        "max_member_count": 100,
                    }
                ]
            }
        if action == "get_resource_temp_url":
            return "https://example.com/temp/resource"
        if action == "get_message":
            return {
                "message": {
                    "message_scene": "group",
                    "peer_id": p.get("peer_id", 0),
                    "message_seq": p.get("message_seq", 0),
                    "sender_id": referenced_sender_id,
                    "time": 1,
                    "segments": referenced_segments,
                    "group": {
                        "group_id": p.get("peer_id", 0),
                        "group_name": "test group",
                        "member_count": 2,
                        "max_member_count": 100,
                    },
                    "group_member": {
                        "user_id": referenced_sender_id,
                        "nickname": "TestUser",
                        "sex": "unknown",
                        "group_id": p.get("peer_id", 0),
                        "card": "TestCard",
                        "title": "",
                        "level": 1,
                        "role": "member",
                        "join_time": 1,
                        "last_sent_time": 1,
                    },
                }
            }
        if action == "get_forwarded_messages":
            return {"messages": [], "next_message_seq": 0}
        if action == "get_group_member_list":
            return []
        return {}

    monkeypatch.setattr(MilkyAdapter, "call_http", _fake_call)

    # Stub outbound HTTP so handlers never open live connections.
    async def _fake_post(url: str, **kwargs: Any) -> Any:
        del url, kwargs
        return SimpleNamespace(
            status_code=200,
            text="[]",
            content=b"{}",
            json=[],
            ok=True,
        )

    aiohttpx = _loaded_module("hoshino.util").aiohttpx

    monkeypatch.setattr(aiohttpx, "post", _fake_post)
    monkeypatch.setattr(aiohttpx, "get", _fake_post)
    monkeypatch.setattr(aiohttpx, "head", _fake_post)

    return calls


def _enable_svc(monkeypatch: pytest.MonkeyPatch, name: str) -> None:
    _loaded_services = _loaded_module("hoshino.core.service")._loaded_services
    svc = _loaded_services.get(name)
    if svc is not None:
        monkeypatch.setattr(
            svc,
            "enable_scope",
            set(svc.enable_scope) | {"milky:123456"},
        )


def _send_calls(calls, action="send_group_message"):
    send_calls = [call for call in calls if call["action"] == action]
    assert calls == send_calls
    return send_calls


def _assert_one_send(
    calls: list[dict[str, Any]],
    *,
    action: str = "send_group_message",
    target_key: str = "group_id",
    target_id: int = 123456,
) -> list[dict[str, Any]]:
    assert len(calls) == 1
    call = calls[0]
    assert call["action"] == action
    params = call["params"]
    assert params[target_key] == target_id
    return params["message"]


# ===================================================================
# base
# ===================================================================


class TestBasePlugins:
    @pytest.mark.usefixtures("_nonebot_bootstrap")
    async def test_zai_at_mention_zai_text(self, monkeypatch):
        """zai: on_command('zai') via @mention → text reply."""
        bot = _make_bot()
        event = _at_bot_msg(" 在吗")
        calls = _stub_all_api(monkeypatch)

        await bot.handle_event(event)

        message = _assert_one_send(calls)
        expected = str(_loaded_module("hoshino.core.config").config.zai)
        assert message == [{"type": "text", "data": {"text": expected}}]

    @pytest.mark.usefixtures("_nonebot_bootstrap")
    async def test_zai_no_mention_no_response(self, monkeypatch):
        """zai: bare text without @mention → silent."""
        bot = _make_bot()
        event = _make_group_msg("在吗")
        calls = _stub_all_api(monkeypatch)

        await bot.handle_event(event)
        assert _send_calls(calls) == []

    @pytest.mark.usefixtures("_nonebot_bootstrap")
    async def test_help_command_responds(self, monkeypatch):
        """help: sv.on_alconna(help ...)."""
        bot = _make_bot()
        event = _make_group_msg("help")
        calls = _stub_all_api(monkeypatch)

        await bot.handle_event(event)

        send = _send_calls(calls)
        assert len(send) == 1
        assert send[0]["params"]["group_id"] == 123456
        msg = send[0]["params"]["message"]
        assert any(
            "help" in seg.get("data", {}).get("text", "").lower()
            for seg in msg
            if seg.get("type") == "text"
        )

    @pytest.mark.usefixtures("_nonebot_bootstrap")
    async def test_lssv_permission_or_to_me_blocks(self, monkeypatch):
        """lssv requires ADMIN + to_me(); without @mention → silent."""
        bot = _make_bot()
        event = _make_group_msg("lssv")
        calls = _stub_all_api(monkeypatch)
        await bot.handle_event(event)
        # no @mention → to_me() fails → no response
        assert _send_calls(calls) == []

    @pytest.mark.usefixtures("_nonebot_bootstrap")
    async def test_lssv_superuser_mention_reports_services(self, monkeypatch):
        """service_manage: ADMIN mention command reaches the Milky HTTP API."""
        bot = _make_bot()
        event = _at_bot_msg(" lssv 123456", sender_id=_superuser_id())
        calls = _stub_all_api(monkeypatch)

        await bot.handle_event(event)

        assert [call["action"] for call in calls] == [
            "get_group_list",
            "send_group_message",
        ]
        assert calls[0]["params"] == {"no_cache": False}
        message = calls[1]["params"]["message"]
        text = message[0]["data"]["text"]
        assert "群123456服务一览" in text

    @pytest.mark.usefixtures("_nonebot_bootstrap")
    async def test_ls_group_superuser_reports_joined_groups(self, monkeypatch):
        """ls: the group subcommand uses the adapter-neutral send path."""
        bot = _make_bot()
        event = _at_bot_msg(" ls.group", sender_id=_superuser_id())
        calls = _stub_all_api(monkeypatch)

        await bot.handle_event(event)

        assert [call["action"] for call in calls] == [
            "get_group_list",
            "send_group_message",
        ]
        assert calls[0]["params"] == {"no_cache": False}
        assert calls[1]["params"] == {
            "group_id": 123456,
            "message": [
                {
                    "type": "text",
                    "data": {"text": "| 群号 | 群名 | 共1个群\n123456 test group"},
                }
            ],
        }

    @pytest.mark.usefixtures("_nonebot_bootstrap")
    async def test_check_cookies_superuser_mention_reports_empty(self, monkeypatch):
        """cookies: native superuser command reports deterministic empty state."""
        cookies_module = _loaded_module("hoshino.base.cookies")
        monkeypatch.setattr(cookies_module, "check_all_cookies", lambda: {})
        bot = _make_bot()
        event = _at_bot_msg(" check_cookies all", sender_id=_superuser_id())
        calls = _stub_all_api(monkeypatch)

        await bot.handle_event(event)

        message = _assert_one_send(calls)
        assert message[0]["data"]["text"] == "没有可用的cookies"

    @pytest.mark.usefixtures("_nonebot_bootstrap")
    async def test_testmatchers_superuser_mention_responds(self, monkeypatch):
        """test: native diagnostic command traverses the real send boundary."""
        bot = _make_bot()
        event = _at_bot_msg(" testmatchers", sender_id=_superuser_id())
        calls = _stub_all_api(monkeypatch)

        await bot.handle_event(event)

        message = _assert_one_send(calls)
        assert "Matcher" in message[0]["data"]["text"]

    @pytest.mark.usefixtures("_nonebot_bootstrap")
    async def test_broadcast_superuser_sends_to_joined_group(self, monkeypatch):
        """broadcast: superuser command sends to every adapter-reported group."""
        broadcast_module = _loaded_module("hoshino.base.broadcast")

        async def no_sleep(delay: float) -> None:
            assert delay == 0.5

        monkeypatch.setattr(broadcast_module, "sleep", no_sleep)
        bot = _make_bot()
        event = _at_bot_msg(" bc hello", sender_id=_superuser_id())
        calls = _stub_all_api(monkeypatch)

        await bot.handle_event(event)

        assert [call["action"] for call in calls] == [
            "get_group_list",
            "send_group_message",
            "send_group_message",
        ]
        assert calls[1]["params"]["group_id"] == 123456
        assert calls[1]["params"]["message"][0]["data"]["text"] == "hello"
        assert "投递成功1个群" in calls[2]["params"]["message"][0]["data"]["text"]

    @pytest.mark.usefixtures("_nonebot_bootstrap")
    async def test_image_reaction_notice_saves_referenced_image(self, monkeypatch):
        """image: a Milky reaction retrieves and saves a trusted image."""
        image_module = _loaded_module("hoshino.base.image")
        captured: dict[str, Any] = {}

        async def fake_save_images(segments, **kwargs):
            captured["segments"] = list(segments)
            captured.update(kwargs)
            return len(segments)

        monkeypatch.setattr(image_module, "_save_images", fake_save_images)
        notice = _make_reaction_notice(face_id="66")
        calls = _stub_all_api(
            monkeypatch,
            referenced_sender_id=_superuser_id(),
            referenced_segments=[
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
        )

        await _make_bot().handle_event(notice)

        message_calls = [call for call in calls if call["action"] == "get_message"]
        assert message_calls == [
            {
                "action": "get_message",
                "params": {
                    "message_scene": "group",
                    "peer_id": 123456,
                    "message_seq": 7001,
                },
            }
        ]
        assert captured["message_id"] == 7001
        assert captured["session_id"] == f"group_123456_{_superuser_id()}"
        assert captured["group_id"] == 123456
        assert captured["is_fav"] is True
        assert len(captured["segments"]) == 1
        assert captured["segments"][0].url == "https://example.com/image.jpg"

    @pytest.mark.usefixtures("_nonebot_bootstrap")
    async def test_image_short_delete_alias_remains_available(
        self, monkeypatch, tmp_path
    ):
        """image: the whitespace-qualified ``st`` alias still deletes a file."""
        image_module = _loaded_module("hoshino.base.image")
        image_dir = tmp_path / "images"
        favourite_dir = tmp_path / "favourites"
        image_dir.mkdir()
        favourite_dir.mkdir()
        image_path = image_dir / "example.jpg"
        image_path.write_bytes(b"image")
        monkeypatch.setattr(image_module, "img_dir", image_dir)
        monkeypatch.setattr(image_module, "fav_dir", favourite_dir)
        bot = _make_bot()
        event = _at_bot_msg(" st example.jpg", sender_id=_superuser_id())
        calls = _stub_all_api(monkeypatch)

        await bot.handle_event(event)

        assert not image_path.exists()
        message = _assert_one_send(calls)
        assert message == [
            {"type": "text", "data": {"text": "删除图片example.jpg成功"}}
        ]


# ===================================================================
# develop
# ===================================================================


class TestDevelopPlugins:
    @pytest.mark.usefixtures("_nonebot_bootstrap")
    async def test_say_command_uses_only_the_compact_parsed_argument(self, monkeypatch):
        bot = _make_bot()
        event = _make_group_msg("sayhi")
        calls = _stub_all_api(monkeypatch)

        await bot.handle_event(event)

        send = _send_calls(calls)
        assert len(send) == 1
        p = send[0]["params"]
        assert p["group_id"] == 123456
        msg = p["message"]
        texts = [seg["data"]["text"] for seg in msg if seg["type"] == "text"]
        assert texts == ["hi"]

    @pytest.mark.usefixtures("_nonebot_bootstrap")
    async def test_server_info_superuser_responds(self, monkeypatch):
        """server_info: native superuser command sends its status report."""
        bot = _make_bot()
        event = _at_bot_msg(" 状态", sender_id=_superuser_id())
        calls = _stub_all_api(monkeypatch)

        await bot.handle_event(event)

        message = _assert_one_send(calls)
        assert "服务CPU使用" in message[0]["data"]["text"]


# ===================================================================
# entertainment
# ===================================================================


class TestEntertainmentPlugins:
    @pytest.mark.usefixtures("_nonebot_bootstrap")
    async def test_dice_regex_responds(self, monkeypatch):
        bot = _make_bot()
        event = _make_group_msg("rr1d6")
        calls = _stub_all_api(monkeypatch)

        await bot.handle_event(event)

        message = _assert_one_send(calls)
        assert message[0]["data"]["text"].startswith("本次掷骰结果为: ")

    @pytest.mark.usefixtures("_nonebot_bootstrap")
    async def test_dice_rejects_nonsense(self, monkeypatch):
        bot = _make_bot()
        event = _make_group_msg("xyz123")
        calls = _stub_all_api(monkeypatch)
        await bot.handle_event(event)
        assert _send_calls(calls) == []

    @pytest.mark.usefixtures("_nonebot_bootstrap")
    async def test_bihua_enabled_sends_image(self, monkeypatch):
        """bihua: enabled service resolves a configured image."""
        bihua_module = _loaded_module("hoshino.modules.entertainment.bihua")
        monkeypatch.setattr(bihua_module, "bihuas", {"test": ".png"})
        _enable_svc(monkeypatch, "bihua")
        bot = _make_bot()
        event = _make_group_msg("bihuatest")
        calls = _stub_all_api(monkeypatch)

        await bot.handle_event(event)

        message = _assert_one_send(calls)
        assert message == [
            {
                "type": "image",
                "data": {
                    "uri": "https://bihua.bleatingsheep.org/meme/test.png",
                    "summary": None,
                    "sub_type": "normal",
                },
            }
        ]


# ===================================================================
# interactive
# ===================================================================


class TestInteractivePlugins:
    @pytest.mark.usefixtures("_nonebot_bootstrap")
    @pytest.mark.parametrize(
        ("prompt", "choices"),
        (
            ("选择A还是B", ("A", "B")),
            ("选咖啡还是茶", ("咖啡", "茶")),
            ("选择a or b", ("a", "b")),
            ("choose apple or orange", ("apple", "orange")),
            ("选A还是B还是C", ("A", "B", "C")),
        ),
    )
    async def test_chooseone_regex_responds(self, monkeypatch, prompt, choices):
        """chooseone parses natural Chinese and English choice phrases."""
        bot = _make_bot()
        event = _make_group_msg(prompt)
        calls = _stub_all_api(monkeypatch)

        await bot.handle_event(event)

        message = _assert_one_send(calls)
        text = message[0]["data"]["text"]
        assert text.startswith("让我看看选什么好呢：\n")
        for index, choice in enumerate(choices, start=1):
            assert f"{index}. {choice}" in text
        assert "最终选择" in text

    @pytest.mark.usefixtures("_nonebot_bootstrap")
    async def test_chooseone_private_responds(self, monkeypatch):
        """chooseone: only_group=False — friend event sends a private reply."""
        bot = _make_bot()
        event = _make_friend_msg("choose a or b")
        calls = _stub_all_api(monkeypatch)

        await bot.handle_event(event)

        message = _assert_one_send(
            calls,
            action="send_private_message",
            target_key="user_id",
            target_id=42,
        )
        assert message[0]["data"]["text"].startswith(
            "让我看看选什么好呢：\n1. a\n2. b\n"
        )

    @pytest.mark.usefixtures("_nonebot_bootstrap")
    async def test_foods_enabled_text_image(self, monkeypatch, tmp_path):
        """foods: enabled → text + image segments."""
        foods_mod = _loaded_module("hoshino.modules.interactive.foods")
        # Ensure at least one food image exists (module was loaded at
        # session scope and foods list was already computed).
        foods_dir = tmp_path / "images"
        foods_dir.mkdir()
        PILImage.new("RGB", (1, 1)).save(foods_dir / "test.png")
        monkeypatch.setattr(foods_mod, "foods", [foods_dir / "test.png"])
        _enable_svc(monkeypatch, "foods")
        bot = _make_bot()
        event = _make_group_msg("今天吃什么")
        calls = _stub_all_api(monkeypatch)

        await bot.handle_event(event)

        message = _assert_one_send(calls)
        texts = [seg["data"]["text"] for seg in message if seg["type"] == "text"]
        images = [seg["data"]["uri"] for seg in message if seg["type"] == "image"]
        assert texts[-1].endswith("今天吃test吧! \n")
        assert len(images) == 1
        assert images[0].startswith("base64://")

    @pytest.mark.usefixtures("_nonebot_bootstrap")
    async def test_emojimix_enabled_text_sends_image(self, monkeypatch):
        """emojimix: two supported emoji dispatch through native on_message."""
        _enable_svc(monkeypatch, "emojimix")
        bot = _make_bot()
        event = _make_group_msg("😀😃")
        calls = _stub_all_api(monkeypatch)

        await bot.handle_event(event)

        message = _assert_one_send(calls)
        assert message == [
            {
                "type": "image",
                "data": {
                    "uri": (
                        "https://www.gstatic.com/android/keyboard/emojikitchen/"
                        "20210521/u1f600/u1f600_u1f603.png"
                    ),
                    "summary": None,
                    "sub_type": "normal",
                },
            }
        ]

    @pytest.mark.usefixtures("_nonebot_bootstrap")
    async def test_steam_enabled_list_responds(self, monkeypatch):
        """steam: its full command is not consumed by the ``st`` image alias."""
        steam_module = _loaded_module("hoshino.modules.interactive.steam")
        monkeypatch.setattr(steam_module, "sub", {"subscribes": {}})
        monkeypatch.setattr(steam_module, "playing_state", {})
        _enable_svc(monkeypatch, "steam")
        bot = _make_bot()
        event = _make_group_msg("steam订阅列表")
        calls = _stub_all_api(monkeypatch)

        await bot.handle_event(event)

        message = _assert_one_send(calls)
        assert message == [{"type": "text", "data": {"text": "======steam======\n"}}]

    @pytest.mark.usefixtures("_nonebot_bootstrap")
    async def test_qa_group_list_responds(self, monkeypatch):
        """QA: a group can list its saved questions through the real matcher."""
        bot = _make_bot()
        event = _make_group_msg("看看有人问")
        calls = _stub_all_api(monkeypatch)

        await bot.handle_event(event)

        send = _send_calls(calls)
        assert len(send) == 1
        assert send[0]["params"]["group_id"] == 123456
        text = send[0]["params"]["message"][0]["data"]["text"]
        assert '该群设置的"有人问"有:' in text

    @pytest.mark.usefixtures("_nonebot_bootstrap")
    async def test_alisten_enabled_missing_config_responds(self, monkeypatch):
        """alisten: enabled command reports a missing deterministic config."""
        _enable_svc(monkeypatch, "alisten")
        bot = _make_bot()
        event = _make_group_msg("听歌房用户")
        calls = _stub_all_api(monkeypatch)

        await bot.handle_event(event)

        send = _send_calls(calls)
        assert len(send) == 1
        assert send[0]["params"]["group_id"] == 123456
        text = send[0]["params"]["message"][0]["data"]["text"]
        assert text == "当前没有配置听歌房"

    @pytest.mark.usefixtures("_nonebot_bootstrap")
    async def test_qbitorrent_enabled_missing_config_responds(self, monkeypatch):
        """qbitorrent: enabled command reports a missing deterministic config."""
        _enable_svc(monkeypatch, "qbitorrent")
        bot = _make_bot()
        event = _make_group_msg("下载列表")
        calls = _stub_all_api(monkeypatch)

        await bot.handle_event(event)

        send = _send_calls(calls)
        assert len(send) == 1
        assert send[0]["params"]["group_id"] == 123456
        text = send[0]["params"]["message"][0]["data"]["text"]
        assert "qbt配置" in text


# ===================================================================
# information
# ===================================================================


class TestInformationPlugins:
    @pytest.mark.usefixtures("_nonebot_bootstrap")
    async def test_weibo_reaction_notice_uses_cached_post(self, monkeypatch):
        """weibo: Milky reaction notice fetches the message and saves cached post."""
        weibo_resolve = _loaded_module("hoshino.modules.information.weibo.resolve")
        notice = _make_reaction_notice()
        calls = _stub_all_api(
            monkeypatch,
            referenced_text="https://weibo.com/123/abc",
            referenced_sender_id=_superuser_id(),
        )
        _enable_svc(monkeypatch, "weibo")
        appended: list[tuple[str, str]] = []
        monkeypatch.setattr(
            weibo_resolve, "get_cached_weibo_uid_id", lambda _: "123_abc"
        )
        monkeypatch.setattr(
            weibo_resolve,
            "append_fav",
            lambda uid, post_id: appended.append((uid, post_id)) or True,
        )

        async def fake_send_to_superuser(message: str) -> None:
            assert "微博收藏新增" in message

        monkeypatch.setattr(weibo_resolve, "send_to_superuser", fake_send_to_superuser)

        await _make_bot().handle_event(notice)

        assert calls == [
            {
                "action": "get_message",
                "params": {
                    "message_scene": "group",
                    "peer_id": 123456,
                    "message_seq": 7001,
                },
            }
        ]
        assert appended == [("123", "abc")]

    @pytest.mark.usefixtures("_nonebot_bootstrap")
    async def test_weibo_enabled_empty_list_responds(self, monkeypatch):
        """weibo: enabled service reports an empty subscription list."""
        _enable_svc(monkeypatch, "weibo")
        bot = _make_bot()
        event = _make_group_msg("微博订阅")
        calls = _stub_all_api(monkeypatch)

        await bot.handle_event(event)

        send = _send_calls(calls)
        assert len(send) == 1
        assert send[0]["params"]["group_id"] == 123456
        text = send[0]["params"]["message"][0]["data"]["text"]
        assert text == "本群没有订阅微博用户"

    @pytest.mark.usefixtures("_nonebot_bootstrap")
    async def test_bilireq_enabled_empty_list_responds(self, monkeypatch):
        """bilireq: a longer alias is not consumed as a compact add command."""
        _enable_svc(monkeypatch, "bilireq")
        bot = _make_bot()
        event = _make_group_msg("订阅动态列表")
        calls = _stub_all_api(monkeypatch)

        await bot.handle_event(event)

        send = _send_calls(calls)
        assert len(send) == 1
        assert send[0]["params"]["group_id"] == 123456
        text = send[0]["params"]["message"][0]["data"]["text"]
        assert text == "本群没有订阅动态"

    @pytest.mark.usefixtures("_nonebot_bootstrap")
    async def test_pushlive_enabled_empty_list_responds(self, monkeypatch):
        """pushlive: enabled service reports an empty subscription list."""
        _enable_svc(monkeypatch, "pushlive")
        bot = _make_bot()
        event = _make_group_msg("直播订阅")
        calls = _stub_all_api(monkeypatch)

        await bot.handle_event(event)

        send = _send_calls(calls)
        assert len(send) == 1
        assert send[0]["params"]["group_id"] == 123456
        text = send[0]["params"]["message"][0]["data"]["text"]
        assert text == "本群没有订阅直播间"

    @pytest.mark.usefixtures("_nonebot_bootstrap")
    async def test_resolve_bv_dispatches_stubbed_video(self, monkeypatch):
        """resolve: a BV identifier reaches the resolver and sends its result."""
        resolve_module = _loaded_module("hoshino.modules.information.resolve")
        message_utils = _loaded_module("hoshino.util.message")

        async def fake_resolve(name: str, url: str, matched: Any) -> bool:
            assert name == "bv"
            assert url == "BV1Q541167Qg"
            assert matched.group(0) == url
            await message_utils.send("resolved video")
            return True

        monkeypatch.setattr(resolve_module, "resolve_bilibili", fake_resolve)
        _enable_svc(monkeypatch, "resolve")
        bot = _make_bot()
        event = _make_group_msg("BV1Q541167Qg")
        calls = _stub_all_api(monkeypatch)

        await bot.handle_event(event)

        message = _assert_one_send(calls)
        assert message == [{"type": "text", "data": {"text": "resolved video"}}]


# ===================================================================
# tools
# ===================================================================


class TestToolsPlugins:
    @pytest.mark.usefixtures("_nonebot_bootstrap")
    async def test_b64_enabled_encrypt_text(self, monkeypatch):
        _enable_svc(monkeypatch, "b64")
        bot = _make_bot()
        event = _make_group_msg("b64加密hello")
        calls = _stub_all_api(monkeypatch)

        await bot.handle_event(event)

        send = _send_calls(calls)
        assert len(send) == 1
        p = send[0]["params"]
        assert p["group_id"] == 123456
        msg = p["message"]
        texts = [seg["data"]["text"] for seg in msg if seg["type"] == "text"]
        assert any("aGVsbG8=" in text for text in texts)

    @pytest.mark.usefixtures("_nonebot_bootstrap")
    async def test_b64_enabled_decrypt_text(self, monkeypatch):
        _enable_svc(monkeypatch, "b64")
        bot = _make_bot()
        event = _make_group_msg("b64 aGVsbG8=")
        calls = _stub_all_api(monkeypatch)

        await bot.handle_event(event)

        send = _send_calls(calls)
        assert len(send) == 1
        p = send[0]["params"]
        assert p["group_id"] == 123456
        msg = p["message"]
        texts = [seg["data"]["text"] for seg in msg if seg["type"] == "text"]
        assert any("hello" in text for text in texts)

    @pytest.mark.usefixtures("_nonebot_bootstrap")
    async def test_b64_enabled_encrypt_private_text(self, monkeypatch):
        """b64: only_group=False private command sends a private reply."""
        _enable_svc(monkeypatch, "b64")
        bot = _make_bot()
        event = _make_friend_msg("b64加密 hello")
        calls = _stub_all_api(monkeypatch)

        await bot.handle_event(event)

        message = _assert_one_send(
            calls,
            action="send_private_message",
            target_key="user_id",
            target_id=42,
        )
        assert message[0]["data"]["text"] == "aGVsbG8="

    @pytest.mark.usefixtures("_nonebot_bootstrap")
    async def test_nbnhhsh_regex_matches_stubbed(self, monkeypatch):
        """nbnhhsh: ??word — external API stubbed, check dispatch."""
        bot = _make_bot()
        event = _make_group_msg("??abc")
        calls = _stub_all_api(monkeypatch)

        await bot.handle_event(event)
        # nbnhhsh handler calls aiohttpx.post which is stubbed;
        # the handler runs but may not send_group_message (depends on API response)
        send = _send_calls(calls)
        assert len(send) == 1
        assert send[0]["params"]["group_id"] == 123456
        text = send[0]["params"]["message"][0]["data"]["text"]
        assert text == "abc: 没有结果"

    @pytest.mark.usefixtures("_nonebot_bootstrap")
    async def test_nbnhhsh_rejects_plain(self, monkeypatch):
        bot = _make_bot()
        event = _make_group_msg("hello")
        calls = _stub_all_api(monkeypatch)
        await bot.handle_event(event)
        assert _send_calls(calls) == []

    @pytest.mark.usefixtures("_nonebot_bootstrap")
    async def test_nbnhhsh_private_responds(self, monkeypatch):
        """nbnhhsh: only_group=False — friend event sends a private reply."""
        bot = _make_bot()
        event = _make_friend_msg("??abc")
        calls = _stub_all_api(monkeypatch)

        await bot.handle_event(event)

        message = _assert_one_send(
            calls,
            action="send_private_message",
            target_key="user_id",
            target_id=42,
        )
        text = message[0]["data"]["text"]
        assert text == "abc: 没有结果"


class TestBlackPlugin:
    @pytest.mark.usefixtures("_nonebot_bootstrap")
    async def test_black_superuser_starts_interactive_prompt(self, monkeypatch):
        """black: superuser command enters its real multi-step matcher flow."""
        bot = _make_bot()
        event = _at_bot_msg(" 拉黑", sender_id=_superuser_id())
        calls = _stub_all_api(monkeypatch)

        await bot.handle_event(event)

        message = _assert_one_send(calls)
        assert "请输入要拉黑的id" in message[0]["data"]["text"]
