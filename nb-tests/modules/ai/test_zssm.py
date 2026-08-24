"""zssm（这是什么）插件测试：文本/回复/图片/权限与错误路径。

zssm 使用 Agent + web 工具（web_search / web_fetch / browser_use），
测试 stub _build_zssm_agent 返回 FakeAgent，使 run 在单轮内完成。
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from nonebot.adapters.milky import Bot as MilkyBot
from nonebot.adapters.milky.config import ClientInfo
from nonebot.adapters.milky.event import GroupMessageEvent as MilkyGroupMessageEvent
from nonebot.adapters.milky.model.api import MessageResponse
from pydantic_ai.usage import RunUsage

from _helpers import next_seq
from hoshino.ai.config import AIConfig


@pytest.fixture(autouse=True)
def _fresh_agent_cache(monkeypatch):
    from hoshino.modules.ai import zssm

    monkeypatch.setattr(zssm, "_agent_cache", {})


_DEFAULT_MODEL_TEXT = '{"output":"这是一张显卡","keywords":["显卡"],"blocked":false}'


def _milky_group(text, *, user_id=42, role="member", group_id=123456, reply=None):
    from nonebot import get_adapters
    from nonebot.adapters.milky import Adapter as MilkyAdapter

    adapter = get_adapters()[MilkyAdapter.get_name()]
    bot = MilkyBot(adapter, self_id="10000", info=ClientInfo())
    event = adapter.json_to_event(
        {
            "event_type": "message_receive",
            "time": 1,
            "self_id": 10000,
            "data": {
                "message_scene": "group",
                "peer_id": group_id,
                "message_seq": next_seq(),
                "sender_id": user_id,
                "time": 1,
                "segments": [{"type": "text", "data": {"text": text}}],
                "group": {
                    "group_id": group_id,
                    "group_name": "test group",
                    "member_count": 2,
                    "max_member_count": 100,
                },
                "group_member": {
                    "user_id": user_id,
                    "nickname": "Alice",
                    "sex": "unknown",
                    "group_id": group_id,
                    "card": "Alice member",
                    "title": "",
                    "level": 1,
                    "role": role,
                    "join_time": 1,
                    "last_sent_time": 1,
                },
            },
            **({"reply": reply} if reply is not None else {}),
        }
    )
    assert isinstance(event, MilkyGroupMessageEvent)
    event.to_me = False
    return bot, event


def _milky_reply(sender_id, text, seq=77):
    return {
        "message_scene": "group",
        "peer_id": 123456,
        "message_seq": seq,
        "sender_id": sender_id,
        "time": 1,
        "segments": [{"type": "text", "data": {"text": text}}],
    }


class FakeResult:
    def __init__(self, data=_DEFAULT_MODEL_TEXT):
        self.data = data
        self.output = data
        self._usage = RunUsage(input_tokens=5, output_tokens=3, requests=1)

    def all_messages(self):
        return []

    def with_prefix(self, prefix):
        return FakeResult(self.data)

    def usage(self):
        return self._usage


class FakeAgentRun:
    def __init__(self, result):
        self._result = result
        self.ctx = object()
        self.result = None
        self._count = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._count >= 1:
            self.result = self._result
            raise StopAsyncIteration
        self._count += 1
        return object()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class FakeAgent:
    def __init__(self, text=_DEFAULT_MODEL_TEXT):
        self._result = FakeResult(text)
        self.prompt = None

    def iter(self, prompt, **kwargs):
        self.prompt = prompt
        return FakeAgentRun(self._result)


def _stub_env(monkeypatch, tmp_store, *, model_text=_DEFAULT_MODEL_TEXT, with_vision=False):
    from hoshino.modules.ai import zssm

    monkeypatch.setattr(zssm.sv, "check_enabled", lambda scope: True)
    config = AIConfig(default="openai")
    monkeypatch.setattr(zssm, "get_config", lambda: config)
    tmp_store.upsert_provider_row(
        provider_id="openai",
        url="https://api.example.com/v1",
        key="sk-abcdefghij",
        kind="openai_chat",
        default_text_model="gpt-4o-mini",
    )
    tmp_store.upsert_provider_model("openai", "gpt-4o-mini", "text")
    if with_vision:
        tmp_store.set_global_value("default_vision_provider", "openai")
        tmp_store.set_global_value("default_vision_model", "gpt-4o")
    fake = FakeAgent(model_text)
    monkeypatch.setattr(zssm, "_build_zssm_agent", lambda *a, **k: fake)
    sent = []

    async def fake_send(self, *, group_id, message):
        sent.append((group_id, message))
        return MessageResponse(message_seq=8, time=1)

    monkeypatch.setattr(MilkyBot, "send_group_message", fake_send)
    return fake, sent


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_zssm_direct_text_explains(monkeypatch, tmp_store):
    fake, sent = _stub_env(monkeypatch, tmp_store)
    bot, event = _milky_group("zssm hello world --text")
    await bot.handle_event(event)
    payload = json.loads(fake.prompt)
    assert payload["target"] == "hello world"
    assert payload["focus"] == ""
    text = sent[0][1].extract_plain_text()
    assert "关键词：显卡" in text and "这是一张显卡" in text


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_zssm_reply_target_and_focus(monkeypatch, tmp_store):
    fake, sent = _stub_env(monkeypatch, tmp_store)
    bot, event = _milky_group("zssm 显卡 --text", reply=_milky_reply(7, "RTX 4090 好贵啊"))
    await bot.handle_event(event)
    payload = json.loads(fake.prompt)
    assert payload["target"] == "RTX 4090 好贵啊" and payload["focus"] == "显卡"


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_zssm_empty_target_shows_usage(monkeypatch, tmp_store):
    fake, sent = _stub_env(monkeypatch, tmp_store)
    bot, event = _milky_group("zssm")
    await bot.handle_event(event)
    assert "用法：zssm" in sent[0][1].extract_plain_text()
    assert fake.prompt is None


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_zssm_without_provider_shows_error(monkeypatch, tmp_store):
    fake, sent = _stub_env(monkeypatch, tmp_store)
    tmp_store.delete_provider_row("openai")
    bot, event = _milky_group("zssm 随便什么")
    await bot.handle_event(event)
    assert "AI 服务未配置任何 provider" in sent[0][1].extract_plain_text()
    assert fake.prompt is None


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_zssm_urls_passed_to_agent(monkeypatch, tmp_store):
    fake, sent = _stub_env(monkeypatch, tmp_store)
    bot, event = _milky_group("zssm 看看 https://example.com/page 是什么 --text")
    await bot.handle_event(event)
    payload = json.loads(fake.prompt)
    assert "https://example.com/page" in payload.get("urls_in_target", [])


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_zssm_image_with_vision_describes(monkeypatch, tmp_store):
    from hoshino.modules.ai import zssm

    fake, sent = _stub_env(monkeypatch, tmp_store, with_vision=True)

    async def fake_images(bot, event):
        return [SimpleNamespace(url="https://x/a.png")]

    monkeypatch.setattr(zssm.image_mod, "event_images", fake_images)

    async def fake_desc(url, **kw):
        return "图片里有一张显卡"

    monkeypatch.setattr(zssm.image_mod, "describe_image_url", fake_desc)
    bot, event = _milky_group("zssm 这图是啥 --text")
    await bot.handle_event(event)
    payload = json.loads(fake.prompt)
    assert payload["image_descriptions"] == "图片1：图片里有一张显卡"


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_zssm_image_without_vision_hints(monkeypatch, tmp_store):
    from hoshino.modules.ai import zssm

    fake, sent = _stub_env(monkeypatch, tmp_store, with_vision=False)

    async def fake_images(bot, event):
        return [SimpleNamespace(url="https://x/a.png")]

    monkeypatch.setattr(zssm.image_mod, "event_images", fake_images)
    bot, event = _milky_group("zssm --text")
    await bot.handle_event(event)
    assert "无法识别图片内容" in sent[0][1].extract_plain_text()
    assert fake.prompt is None


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_zssm_default_renders_markdown_image(monkeypatch, tmp_store):
    from hoshino.modules.ai import zssm

    fake, sent = _stub_env(monkeypatch, tmp_store)

    async def fake_render(md, cfg):
        return b"FAKEPNG"

    monkeypatch.setattr(zssm.rendering, "render_markdown", fake_render)
    bot, event = _milky_group("zssm hello")
    await bot.handle_event(event)
    assert [s.type for s in sent[0][1]] == ["image"]


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_zssm_render_failure_falls_back_to_text(monkeypatch, tmp_store):
    from hoshino.modules.ai import zssm

    fake, sent = _stub_env(monkeypatch, tmp_store)

    async def broken(md, cfg):
        raise RuntimeError("no browser")

    monkeypatch.setattr(zssm.rendering, "render_markdown", broken)
    bot, event = _milky_group("zssm hello")
    await bot.handle_event(event)
    assert [s.type for s in sent[0][1]] == ["text"]


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_zssm_text_flag_skips_render(monkeypatch, tmp_store):
    from hoshino.modules.ai import zssm

    fake, sent = _stub_env(monkeypatch, tmp_store)

    async def nope(md, cfg):
        raise AssertionError("不应触发")

    monkeypatch.setattr(zssm.rendering, "render_markdown", nope)
    bot, event = _milky_group("zssm hello --text")
    await bot.handle_event(event)
    assert json.loads(fake.prompt)["target"] == "hello"
    assert [s.type for s in sent[0][1]] == ["text"]


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_zssm_reply_to_bot_message_sends_once(monkeypatch, tmp_store):
    from hoshino.modules.ai import chat

    fake, sent = _stub_env(monkeypatch, tmp_store)
    monkeypatch.setattr(chat.sv, "check_enabled", lambda scope: True)
    bot, event = _milky_group("zssm 这是什么 --text", reply=_milky_reply(10000, "bot 发的"))
    await bot.handle_event(event)
    assert len(sent) == 1


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_zssm_blocked_response(monkeypatch, tmp_store):
    fake, sent = _stub_env(
        monkeypatch, tmp_store, model_text='{"output":"","keywords":[],"blocked":true}'
    )
    bot, event = _milky_group("zssm 神秘代码 --text")
    await bot.handle_event(event)
    assert "（抱歉，我现在还不会这个）" in sent[0][1].extract_plain_text()


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_zssm_malformed_json_keeps_raw(monkeypatch, tmp_store):
    fake, sent = _stub_env(monkeypatch, tmp_store, model_text="不解释了")
    bot, event = _milky_group("zssm hello --text")
    await bot.handle_event(event)
    assert "不解释了" in sent[0][1].extract_plain_text()


# ------------------------------------------------------- 护栏与错误路径


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_zssm_run_timeout_reports_timeout(monkeypatch, tmp_store):
    """Agent run 超时（多轮工具调用卡住）：回复超时提示。"""
    import asyncio as _asyncio

    from hoshino.modules.ai import zssm

    fake, sent = _stub_env(monkeypatch, tmp_store)
    monkeypatch.setattr(zssm, "_TIMEOUT_SECONDS", 0.05)

    class SlowRun:
        def __init__(self):
            self.ctx = object()
            self.result = None

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        def __aiter__(self):
            return self

        async def __anext__(self):
            await _asyncio.sleep(5)
            raise StopAsyncIteration

    class SlowAgent(FakeAgent):
        def iter(self, prompt, **kwargs):
            self.prompt = prompt
            return SlowRun()

    monkeypatch.setattr(zssm, "_build_zssm_agent", lambda *a, **k: SlowAgent())

    bot, event = _milky_group("zssm 慢慢来 --text")
    await bot.handle_event(event)
    assert "解释超时" in sent[0][1].extract_plain_text()


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_zssm_agent_error_reports_failure(monkeypatch, tmp_store):
    """Agent run 抛异常（模型/工具错误）：回复失败提示。"""
    from hoshino.modules.ai import zssm

    fake, sent = _stub_env(monkeypatch, tmp_store)

    class ErrorRun(FakeAgentRun):
        async def __anext__(self):
            raise RuntimeError("model exploded")

    class ErrorAgent(FakeAgent):
        def iter(self, prompt, **kwargs):
            self.prompt = prompt
            return ErrorRun(self._result)

    monkeypatch.setattr(zssm, "_build_zssm_agent", lambda *a, **k: ErrorAgent())

    bot, event = _milky_group("zssm 试试 --text")
    await bot.handle_event(event)
    assert "解释失败" in sent[0][1].extract_plain_text()


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_zssm_run_none_result_reports_empty(monkeypatch, tmp_store):
    """run 未正常结束（result 为 None）：回复无内容提示。"""
    from hoshino.modules.ai import zssm

    fake, sent = _stub_env(monkeypatch, tmp_store)

    class NoneRun(FakeAgentRun):
        def __init__(self):
            self.ctx = object()
            self.result = None
            self._count = 0

        async def __anext__(self):
            if self._count >= 1:
                raise StopAsyncIteration
            self._count += 1
            return object()

    class NoneAgent(FakeAgent):
        def iter(self, prompt, **kwargs):
            self.prompt = prompt
            return NoneRun()

    monkeypatch.setattr(zssm, "_build_zssm_agent", lambda *a, **k: NoneAgent())

    bot, event = _milky_group("zssm 空结果 --text")
    await bot.handle_event(event)
    assert "模型没有返回内容" in sent[0][1].extract_plain_text()
