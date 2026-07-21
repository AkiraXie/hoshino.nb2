"""Per-plugin Milky behavioral tests — handle_event() + HTTP assertions.

Each matcher-bearing plugin gets 1–2 real-entry cases following
``docs/milky-plugin-test-protocol.md``. Tests patch the registered Milky
adapter's ``call_http`` method to capture ``(action, params)`` records, and
stub handler-owned HTTP clients to prevent live outbound HTTP.

Uses the session-scoped ``_nonebot_bootstrap`` fixture from conftest.py.
"""

from __future__ import annotations

from typing import Any

import pytest
from nonebot import get_adapters
from nonebot.adapters.milky import Adapter as MilkyAdapter
from nonebot.adapters.milky import Bot as MilkyBot
from nonebot.adapters.milky.config import ClientInfo
from nonebot.adapters.milky.event import FriendMessageEvent as MilkyFriendMessageEvent
from nonebot.adapters.milky.event import GroupMessageEvent as MilkyGroupMessageEvent

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

_seq = 100000


def _next_seq() -> int:
    global _seq
    _seq += 1
    return _seq


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
) -> list[dict[str, Any]]:
    """Capture the registered adapter's Milky HTTP boundary.

    Also stub ``hoshino.util.aiohttpx.post`` so handlers that perform
    outbound HTTP lookups do not open live connections.
    """

    calls: list[dict[str, Any]] = []

    async def _fake_call(
        self: MilkyAdapter,
        info: ClientInfo,
        action: str,
        params: dict | None = None,
    ) -> dict[str, Any]:
        p = dict(params or {})
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
                "message_scene": "group",
                "peer_id": p.get("peer_id", 0),
                "message_seq": p.get("message_seq", 0),
                "sender_id": 42,
                "time": 1,
                "segments": [{"type": "text", "data": {"text": "stubbed"}}],
                "sender": {"user_id": 42, "nickname": "T", "card": "T"},
            }
        if action == "get_forwarded_messages":
            return []
        if action == "get_group_member_list":
            return []
        return {}

    monkeypatch.setattr(MilkyAdapter, "call_http", _fake_call)

    # Stub outbound HTTP so handlers never open live connections.
    async def _fake_post(url: str, **kwargs: Any) -> Any:
        del url, kwargs
        return type(
            "Response",
            (),
            {
                "status_code": 200,
                "text": "[]",
                "content": b"{}",
                "json": [],
            },
        )()

    from hoshino.util import aiohttpx

    monkeypatch.setattr(aiohttpx, "post", _fake_post)
    monkeypatch.setattr(aiohttpx, "get", _fake_post)
    monkeypatch.setattr(aiohttpx, "head", _fake_post)

    return calls


def _enable_svc(monkeypatch: pytest.MonkeyPatch, name: str) -> None:
    from hoshino.service import _loaded_services

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

        send = _send_calls(calls)
        assert len(send) == 1
        p = send[0]["params"]
        assert p["group_id"] == 123456
        msg = p["message"]
        types = [seg.get("type") for seg in msg]
        assert "text" in types

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
    async def test_check_cookies_superuser_mention_reports_empty(self, monkeypatch):
        """cookies: native superuser command reports deterministic empty state."""
        import hoshino.base.cookies as cookies_module

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
        import hoshino.base.broadcast as broadcast_module

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


# ===================================================================
# develop
# ===================================================================


class TestDevelopPlugins:
    @pytest.mark.usefixtures("_nonebot_bootstrap")
    async def test_say_alconna_responds(self, monkeypatch):
        bot = _make_bot()
        event = _make_group_msg("say hi")
        calls = _stub_all_api(monkeypatch)

        await bot.handle_event(event)

        send = _send_calls(calls)
        assert len(send) == 1
        p = send[0]["params"]
        assert p["group_id"] == 123456
        msg = p["message"]
        texts = " ".join(seg["data"]["text"] for seg in msg if seg["type"] == "text")
        assert "hi" in texts

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

        send = _send_calls(calls)
        assert len(send) == 1
        assert send[0]["params"]["group_id"] == 123456

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
        import hoshino.modules.entertainment.bihua as bihua_module

        monkeypatch.setattr(bihua_module, "bihuas", {"test": ".png"})
        _enable_svc(monkeypatch, "bihua")
        bot = _make_bot()
        event = _make_group_msg("bihua test")
        calls = _stub_all_api(monkeypatch)

        await bot.handle_event(event)

        send = _send_calls(calls)
        assert len(send) == 1
        assert send[0]["params"]["group_id"] == 123456
        assert send[0]["params"]["message"][0]["type"] == "image"

    @pytest.mark.usefixtures("_nonebot_bootstrap")
    async def test_coser_enabled_mention_sends_image(self, monkeypatch):
        """coser: enabled mention command uses its stubbed external API."""
        import hoshino.modules.entertainment.coser as coser_module

        async def fake_get(url: str) -> Any:
            del url
            return type(
                "Response", (), {"json": {"text": "https://example.com/coser.jpg"}}
            )()

        _enable_svc(monkeypatch, "coser")
        bot = _make_bot()
        event = _at_bot_msg(" coser")
        calls = _stub_all_api(monkeypatch)
        monkeypatch.setattr(coser_module.aiohttpx, "get", fake_get)

        await bot.handle_event(event)

        send = _send_calls(calls)
        assert len(send) == 1
        assert send[0]["params"]["group_id"] == 123456
        assert send[0]["params"]["message"][0]["type"] == "image"


# ===================================================================
# interactive
# ===================================================================


class TestInteractivePlugins:
    @pytest.mark.usefixtures("_nonebot_bootstrap")
    async def test_chooseone_alconna_responds(self, monkeypatch):
        """chooseone: sv.on_alconna(选择 A还是B) — handler needs '还是'."""
        bot = _make_bot()
        event = _make_group_msg("选择 A还是B")
        calls = _stub_all_api(monkeypatch)

        await bot.handle_event(event)

        send = _send_calls(calls)
        assert len(send) == 1
        assert send[0]["params"]["group_id"] == 123456

    @pytest.mark.usefixtures("_nonebot_bootstrap")
    async def test_chooseone_private_responds(self, monkeypatch):
        """chooseone: only_group=False — friend event sends a private reply."""
        bot = _make_bot()
        event = _make_friend_msg("选择 A还是B")
        calls = _stub_all_api(monkeypatch)

        await bot.handle_event(event)

        message = _assert_one_send(
            calls,
            action="send_private_message",
            target_key="user_id",
            target_id=42,
        )
        assert "您的选项是" in message[0]["data"]["text"]

    @pytest.mark.usefixtures("_nonebot_bootstrap")
    async def test_foods_enabled_text_image(self, monkeypatch, tmp_path):
        """foods: enabled → text + image segments."""
        import hoshino.modules.interactive.foods as foods_mod

        # Ensure at least one food image exists (module was loaded at
        # session scope and foods list was already computed).
        foods_dir = tmp_path / "images"
        foods_dir.mkdir()
        from PIL import Image

        Image.new("RGB", (1, 1)).save(foods_dir / "test.png")
        monkeypatch.setattr(foods_mod, "foods", [foods_dir / "test.png"])
        _enable_svc(monkeypatch, "foods")
        bot = _make_bot()
        event = _make_group_msg("今天吃什么")
        calls = _stub_all_api(monkeypatch)

        await bot.handle_event(event)

        send = _send_calls(calls)
        assert len(send) == 1
        p = send[0]["params"]
        assert p["group_id"] == 123456
        msg = p["message"]
        types = [seg.get("type") for seg in msg]
        assert "text" in types
        assert "image" in types

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
        """bilireq: enabled service reports an empty subscription list."""
        _enable_svc(monkeypatch, "bilireq")
        bot = _make_bot()
        event = _make_group_msg("本群动态订阅")
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
        assert text.startswith("本群没有")
        assert "直播订阅" in text


# ===================================================================
# tools
# ===================================================================


class TestToolsPlugins:
    @pytest.mark.usefixtures("_nonebot_bootstrap")
    async def test_b64_enabled_encrypt_text(self, monkeypatch):
        _enable_svc(monkeypatch, "b64")
        bot = _make_bot()
        event = _make_group_msg("b64加密 hello")
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
