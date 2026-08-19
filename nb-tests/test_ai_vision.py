"""AI vision e2e 测试：chat 含图流程走真实 NoneBot dispatch 路径。

milky 事件 + stub build_agent/render/send，验证 vision 描述注入、mask 提示、
无图回退等用户可见行为。
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from conftest import next_seq

pytestmark = pytest.mark.usefixtures("_clear_uninfo_cache")


# ------------------------------------------------------------ helpers


def _milky_group(
    text: str,
    *,
    user_id: int = 7,
    role: str = "admin",
    group_id: int = 123456,
):
    from nonebot import get_adapters
    from nonebot.adapters.milky import Adapter as MilkyAdapter
    from nonebot.adapters.milky import Bot as MilkyBot
    from nonebot.adapters.milky.config import ClientInfo

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
        }
    )
    event.to_me = False
    return bot, event


def _stub_env(monkeypatch, tmp_store, *, vision_model: str = "", render_error: bool = False):
    """配置 openai provider（可选全局默认 vision）+ stub render/send。"""
    from nonebot.adapters.milky import Bot as MilkyBot
    from nonebot.adapters.milky.model.api import MessageResponse

    from hoshino.ai.config import AIConfig
    from hoshino.modules.ai import chat

    tmp_store.upsert_provider_row(
        provider_id="openai",
        url="https://api.example.com/v1",
        key="sk-abcdefghij",
        kind="openai_chat",
        default_text_model="gpt-4o-mini",
    )
    tmp_store.upsert_provider_model("openai", "gpt-4o-mini", "text")
    if vision_model:
        tmp_store.set_global_value("default_vision_provider", "openai")
        tmp_store.set_global_value("default_vision_model", vision_model)

    config = AIConfig(default="openai", system_prompt="你是测试助手。")
    monkeypatch.setattr(chat, "get_config", lambda: config)
    monkeypatch.setattr(chat.sv, "check_enabled", lambda scope: True)

    if render_error:

        async def fake_render(md, cfg):
            raise RuntimeError("render boom")

    else:

        async def fake_render(md, cfg):
            return b"FAKEPNG"

    monkeypatch.setattr(chat.rendering, "render_markdown", fake_render)

    sent: list = []

    async def fake_send_group_message(self, *, group_id: int, message):
        sent.append((group_id, message))
        return MessageResponse(message_seq=8, time=1)

    monkeypatch.setattr(MilkyBot, "send_group_message", fake_send_group_message)
    return config, sent


async def _fake_image_segments(bot, event):
    return [SimpleNamespace(url="https://example.com/a.png", path=None, raw=None)]


class _FakeResult:
    def __init__(self, output: str):
        self.output = output
        self._usage = SimpleNamespace(
            requests=1,
            input_tokens=5,
            output_tokens=3,
            cache_read_tokens=0,
            cache_write_tokens=0,
            total_tokens=8,
        )

    def all_messages(self):
        return []

    def usage(self):
        return self._usage


class _FakeAgentRun:
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


class _FakeAgent:
    def __init__(self, result):
        self._result = result

    def iter(self, prompt, **kwargs):
        self.prompt = prompt
        return _FakeAgentRun(self._result)


# ------------------------------------------------------------ e2e tests


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_chat_image_with_vision_describes_and_answers_with_text(monkeypatch, tmp_store):
    """含图 + vision 模型：vision 模型描述图片，text 模型作答。"""
    from hoshino.modules.ai import chat

    _, sent = _stub_env(monkeypatch, tmp_store, vision_model="gpt-4o")
    monkeypatch.setattr(chat, "_event_images", _fake_image_segments)

    async def fake_describe(record, vision_model, content, *, proxy=None):
        return "图里有一只猫"

    monkeypatch.setattr(chat.vision, "describe_images", fake_describe)
    captured: dict = {}

    def fake_build(provider_id, record, model, **kwargs):
        captured["model"] = model
        captured["record"] = record
        return _FakeAgent(_FakeResult("看到了"))

    monkeypatch.setattr(chat.providers, "build_agent", fake_build)

    bot, event = _milky_group("#这是什么")
    await bot.handle_event(event)

    assert captured["model"] == "gpt-4o-mini"  # 作答始终用 text 模型
    assert len(sent) == 1
    assert "未配置 vision 模型" not in sent[0][1].extract_plain_text()


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_chat_image_with_vision_injects_description(monkeypatch, tmp_store):
    """vision 模型描述被注入 prompt，text 模型据此作答。"""
    from hoshino.modules.ai import chat

    _stub_env(monkeypatch, tmp_store, vision_model="gpt-4o")
    monkeypatch.setattr(chat, "_event_images", _fake_image_segments)

    async def fake_describe(record, vision_model, content, *, proxy=None):
        return "图里有一只猫"

    monkeypatch.setattr(chat.vision, "describe_images", fake_describe)
    agent = _FakeAgent(_FakeResult("看到了"))
    monkeypatch.setattr(chat.providers, "build_agent", lambda *a, **k: agent)

    bot, event = _milky_group("#这是什么")
    await bot.handle_event(event)

    prompt = agent.prompt
    assert isinstance(prompt, str)
    assert "[图片描述]" in prompt
    assert "图里有一只猫" in prompt
    assert "这是什么" in prompt


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_chat_image_without_vision_uses_text_and_mask(monkeypatch, tmp_store):
    """有图但无 vision 模型：text 模型 + 回复带"未配置 vision 模型"提示。"""
    from hoshino.modules.ai import chat

    _, sent = _stub_env(monkeypatch, tmp_store, render_error=True)  # 回退纯文本
    monkeypatch.setattr(chat, "_event_images", _fake_image_segments)
    captured: dict = {}

    def fake_build(provider_id, record, model, **kwargs):
        captured["model"] = model
        return _FakeAgent(_FakeResult("回答"))

    monkeypatch.setattr(chat.providers, "build_agent", fake_build)

    bot, event = _milky_group("#你好")
    await bot.handle_event(event)

    assert captured["model"] == "gpt-4o-mini"  # text 模型
    assert len(sent) == 1
    assert "未配置 vision 模型" in sent[0][1].extract_plain_text()


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_chat_text_without_image_uses_text_model(monkeypatch, tmp_store):
    """无图消息即使配了 vision 模型也走 text 模型。"""
    from hoshino.modules.ai import chat

    _stub_env(monkeypatch, tmp_store, vision_model="gpt-4o")

    async def _no_images(bot, event):
        return []

    monkeypatch.setattr(chat, "_event_images", _no_images)
    captured: dict = {}

    def fake_build(provider_id, record, model, **kwargs):
        captured["model"] = model
        return _FakeAgent(_FakeResult("回答"))

    monkeypatch.setattr(chat.providers, "build_agent", fake_build)

    bot, event = _milky_group("#你好")
    await bot.handle_event(event)

    assert captured["model"] == "gpt-4o-mini"
