"""zssm（这是什么）插件测试：文本/回复/图片/权限与错误路径。

zssm 使用 Agent + web 工具 + ZssmOutput 结构化输出，
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


def _make_zssm_output(**kwargs):
    """构造 ZssmOutput 实例。"""
    from hoshino.modules.ai.zssm import ZssmOutput

    defaults = {"output": "这是一张显卡", "keywords": ["显卡"], "blocked": False}
    defaults.update(kwargs)
    return ZssmOutput(**defaults)


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
    def __init__(self, output=None):
        self.output = output or _make_zssm_output()
        self._usage = RunUsage(input_tokens=100, output_tokens=50, requests=1)

    def all_messages(self):
        return []

    @property
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
    def __init__(self, output=None):
        self._result = FakeResult(output)
        self.prompt = None

    def iter(self, prompt, **kwargs):
        self.prompt = prompt
        return FakeAgentRun(self._result)


def _stub_env(monkeypatch, tmp_store, *, zssm_output=None):
    """Stub zssm 环境：_build_zssm_agent 返回 FakeAgent，捕获发送消息。"""
    from hoshino.modules.ai import zssm

    monkeypatch.setattr(zssm.sv, "check_enabled", lambda scope: True)
    config = AIConfig(default="openai")
    monkeypatch.setattr(zssm, "get_config", lambda: config)
    tmp_store.upsert_provider_row(
        provider_id="openai",
        url="https://api.example.com/v1",
        key="sk-abcdefghij",
        kind="openai_chat",
    )
    tmp_store.upsert_provider_model("openai", "gpt-4o-mini", "text")
    tmp_store.set_global_value("default_model_provider", "openai")
    tmp_store.set_global_value("default_model", "gpt-4o-mini")
    fake = FakeAgent(zssm_output)
    monkeypatch.setattr(zssm, "_build_zssm_agent", lambda *a, **k: fake)
    sent: list[tuple[int, object]] = []

    async def fake_send(self, *, group_id, message):
        sent.append((group_id, message))
        return MessageResponse(message_seq=8, time=1)

    monkeypatch.setattr(MilkyBot, "send_group_message", fake_send)
    return fake, sent


# ------------------------------------------------------- 正常路径


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_zssm_direct_text_explains(monkeypatch, tmp_store):
    fake, sent = _stub_env(monkeypatch, tmp_store)
    bot, event = _milky_group("zssm hello world")
    await bot.handle_event(event)
    payload = json.loads(fake.prompt)
    assert payload["target"] == "hello world"
    assert payload["focus"] == ""
    all_text = " ".join(str(s[1]) for s in sent)
    assert "关键词：显卡" in all_text
    assert "这是一张显卡" in all_text


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_zssm_reply_target_and_focus(monkeypatch, tmp_store):
    fake, sent = _stub_env(monkeypatch, tmp_store)
    bot, event = _milky_group("zssm 显卡", reply=_milky_reply(7, "RTX 4090 好贵啊"))
    await bot.handle_event(event)
    payload = json.loads(fake.prompt)
    assert payload["target"] == "RTX 4090 好贵啊" and payload["focus"] == "显卡"


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_zssm_urls_passed_in_prompt(monkeypatch, tmp_store):
    fake, sent = _stub_env(monkeypatch, tmp_store)
    bot, event = _milky_group("zssm 看看 https://example.com/page 是什么")
    await bot.handle_event(event)
    payload = json.loads(fake.prompt)
    assert "https://example.com/page" in payload.get("urls_in_target", [])


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_zssm_image_native_multimodal_prompt(monkeypatch, tmp_store):
    """含图：prompt 为 JSON TextContent + BinaryContent，无 image_descriptions。"""
    from pydantic_ai import BinaryContent
    from pydantic_ai.messages import TextContent

    from hoshino.modules.ai import zssm

    fake, sent = _stub_env(monkeypatch, tmp_store)
    image = BinaryContent(data=b"fakepng", media_type="image/png")

    async def fake_images(bot, event):
        return [SimpleNamespace(url="https://x/a.png")]

    async def fake_parts(images, *, config):
        return [image]

    monkeypatch.setattr(zssm.image_mod, "event_images", fake_images)
    monkeypatch.setattr(zssm.image_mod, "event_image_parts", fake_parts)
    bot, event = _milky_group("zssm 这图是啥")
    await bot.handle_event(event)

    assert isinstance(fake.prompt, list)
    assert isinstance(fake.prompt[0], TextContent)
    payload = json.loads(fake.prompt[0].content)
    assert payload["target"] == "这图是啥"
    assert "image_descriptions" not in payload
    assert fake.prompt[1] is image
    assert len(sent) >= 1


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_zssm_image_only_uses_multimodal(monkeypatch, tmp_store):
    """仅有图片、无文本时仍走原生多模态，不再报无法识别。"""
    from pydantic_ai import BinaryContent
    from pydantic_ai.messages import TextContent

    from hoshino.modules.ai import zssm

    fake, sent = _stub_env(monkeypatch, tmp_store)
    image = BinaryContent(data=b"fakepng", media_type="image/png")

    async def fake_images(bot, event):
        return [SimpleNamespace(url="https://x/a.png")]

    async def fake_parts(images, *, config):
        return [image]

    monkeypatch.setattr(zssm.image_mod, "event_images", fake_images)
    monkeypatch.setattr(zssm.image_mod, "event_image_parts", fake_parts)
    bot, event = _milky_group("zssm")
    await bot.handle_event(event)

    assert isinstance(fake.prompt, list)
    assert isinstance(fake.prompt[0], TextContent)
    payload = json.loads(fake.prompt[0].content)
    assert payload["target"] == ""
    assert "image_descriptions" not in payload
    assert fake.prompt[1] is image
    assert "无法识别图片内容" not in str(sent[0][1])


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_zssm_forward_contains_stats(monkeypatch, tmp_store):
    """转发消息第三条应包含模型/provider/token 统计。"""
    fake, sent = _stub_env(monkeypatch, tmp_store)
    bot, event = _milky_group("zssm hello")
    await bot.handle_event(event)
    all_text = " ".join(str(s[1]) for s in sent)
    assert "openai" in all_text
    assert "gpt-4o-mini" in all_text
    assert "100" in all_text  # input_tokens
    assert "50" in all_text  # output_tokens


# ------------------------------------------------------- 护栏与错误路径
