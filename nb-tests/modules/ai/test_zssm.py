"""zssm（这是什么）插件测试：文本/回复/图片/权限与错误路径。

zssm 使用单次 Model.request，测试 stub _request_explain 返回预设文本+usage。
回复方式为转发聊天记录（关键词 / 解释 / 模型统计）。
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from nonebot.adapters.milky import Bot as MilkyBot
from nonebot.adapters.milky.config import ClientInfo
from nonebot.adapters.milky.event import GroupMessageEvent as MilkyGroupMessageEvent
from nonebot.adapters.milky.model.api import MessageResponse
from pydantic_ai.usage import RequestUsage

from _helpers import next_seq
from hoshino.ai.config import AIConfig


@pytest.fixture(autouse=True)
def _fresh_model_cache(monkeypatch):
    from hoshino.modules.ai import zssm

    monkeypatch.setattr(zssm, "_model_cache", {})


_DEFAULT_MODEL_TEXT = '{"output":"这是一张显卡","keywords":["显卡"],"blocked":false}'
_DEFAULT_USAGE = RequestUsage(input_tokens=100, output_tokens=50, cache_read_tokens=30)


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


def _stub_env(monkeypatch, tmp_store, *, model_text=_DEFAULT_MODEL_TEXT, with_vision=False):
    """Stub zssm 环境：_request_explain 返回预设 (text, usage)，捕获发送消息。"""
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

    captured_prompt: list[str | None] = [None]

    async def fake_request_explain(record, model, user_prompt, *, proxy):
        captured_prompt[0] = user_prompt
        return model_text, _DEFAULT_USAGE

    monkeypatch.setattr(zssm, "_request_explain", fake_request_explain)
    sent: list[tuple[int, object]] = []

    async def fake_send(self, *, group_id, message):
        sent.append((group_id, message))
        return MessageResponse(message_seq=8, time=1)

    monkeypatch.setattr(MilkyBot, "send_group_message", fake_send)
    return captured_prompt, sent


# ------------------------------------------------------- 正常路径


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_zssm_direct_text_explains(monkeypatch, tmp_store):
    prompt, sent = _stub_env(monkeypatch, tmp_store)
    bot, event = _milky_group("zssm hello world")
    await bot.handle_event(event)
    payload = json.loads(prompt[0])
    assert payload["target"] == "hello world"
    assert payload["focus"] == ""
    # 转发消息至少包含关键词和解释
    all_text = " ".join(str(s[1]) for s in sent)
    assert "显卡" in all_text


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_zssm_reply_target_and_focus(monkeypatch, tmp_store):
    prompt, sent = _stub_env(monkeypatch, tmp_store)
    bot, event = _milky_group("zssm 显卡", reply=_milky_reply(7, "RTX 4090 好贵啊"))
    await bot.handle_event(event)
    payload = json.loads(prompt[0])
    assert payload["target"] == "RTX 4090 好贵啊" and payload["focus"] == "显卡"


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_zssm_empty_target_shows_usage(monkeypatch, tmp_store):
    prompt, sent = _stub_env(monkeypatch, tmp_store)
    bot, event = _milky_group("zssm")
    await bot.handle_event(event)
    assert "用法：zssm" in str(sent[0][1])
    assert prompt[0] is None


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_zssm_without_provider_shows_error(monkeypatch, tmp_store):
    prompt, sent = _stub_env(monkeypatch, tmp_store)
    tmp_store.delete_provider_row("openai")
    bot, event = _milky_group("zssm 随便什么")
    await bot.handle_event(event)
    assert "AI 服务未配置任何 provider" in str(sent[0][1])
    assert prompt[0] is None


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_zssm_urls_passed_in_prompt(monkeypatch, tmp_store):
    prompt, sent = _stub_env(monkeypatch, tmp_store)
    bot, event = _milky_group("zssm 看看 https://example.com/page 是什么")
    await bot.handle_event(event)
    payload = json.loads(prompt[0])
    assert "https://example.com/page" in payload.get("urls_in_target", [])


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_zssm_image_with_vision_describes(monkeypatch, tmp_store):
    from hoshino.modules.ai import zssm

    prompt, sent = _stub_env(monkeypatch, tmp_store, with_vision=True)

    async def fake_images(bot, event):
        return [SimpleNamespace(url="https://x/a.png")]

    monkeypatch.setattr(zssm.image_mod, "event_images", fake_images)

    async def fake_desc(url, **kw):
        return "图片里有一张显卡"

    monkeypatch.setattr(zssm.image_mod, "describe_image_url", fake_desc)
    bot, event = _milky_group("zssm 这图是啥")
    await bot.handle_event(event)
    payload = json.loads(prompt[0])
    assert payload["image_descriptions"] == "图片1：图片里有一张显卡"


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_zssm_image_without_vision_hints(monkeypatch, tmp_store):
    from hoshino.modules.ai import zssm

    prompt, sent = _stub_env(monkeypatch, tmp_store, with_vision=False)

    async def fake_images(bot, event):
        return [SimpleNamespace(url="https://x/a.png")]

    monkeypatch.setattr(zssm.image_mod, "event_images", fake_images)
    bot, event = _milky_group("zssm")
    await bot.handle_event(event)
    assert "无法识别图片内容" in str(sent[0][1])
    assert prompt[0] is None


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_zssm_forward_contains_stats(monkeypatch, tmp_store):
    """转发消息第三条应包含模型/provider/token 统计。"""
    prompt, sent = _stub_env(monkeypatch, tmp_store)
    bot, event = _milky_group("zssm hello")
    await bot.handle_event(event)
    # send_group_forward 最终调 send_group_message，消息为 reference node
    all_text = " ".join(str(s[1]) for s in sent)
    assert "openai" in all_text
    assert "gpt-4o-mini" in all_text
    assert "100" in all_text  # input_tokens
    assert "50" in all_text  # output_tokens
    assert "30" in all_text  # cache_read_tokens


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_zssm_blocked_response(monkeypatch, tmp_store):
    prompt, sent = _stub_env(
        monkeypatch, tmp_store, model_text='{"output":"","keywords":[],"blocked":true}'
    )
    bot, event = _milky_group("zssm 神秘代码")
    await bot.handle_event(event)
    all_text = " ".join(str(s[1]) for s in sent)
    assert "（抱歉，我现在还不会这个）" in all_text


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_zssm_malformed_json_keeps_raw(monkeypatch, tmp_store):
    prompt, sent = _stub_env(monkeypatch, tmp_store, model_text="不解释了")
    bot, event = _milky_group("zssm hello")
    await bot.handle_event(event)
    all_text = " ".join(str(s[1]) for s in sent)
    assert "不解释了" in all_text


# ------------------------------------------------------- 护栏与错误路径


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_zssm_timeout_reports_timeout(monkeypatch, tmp_store):
    """Model.request 超时：回复超时提示。"""
    from hoshino.modules.ai import zssm

    prompt, sent = _stub_env(monkeypatch, tmp_store)

    async def timeout_request(record, model, user_prompt, *, proxy):
        raise TimeoutError("model request timed out")

    monkeypatch.setattr(zssm, "_request_explain", timeout_request)
    bot, event = _milky_group("zssm 慢慢来")
    await bot.handle_event(event)
    assert "解释超时" in str(sent[0][1])


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_zssm_model_error_reports_failure(monkeypatch, tmp_store):
    """Model.request 抛异常：回复失败提示。"""
    from hoshino.modules.ai import zssm

    prompt, sent = _stub_env(monkeypatch, tmp_store)

    async def error_request(record, model, user_prompt, *, proxy):
        raise RuntimeError("model exploded")

    monkeypatch.setattr(zssm, "_request_explain", error_request)
    bot, event = _milky_group("zssm 试试")
    await bot.handle_event(event)
    assert "解释失败" in str(sent[0][1])


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_zssm_empty_response_reports_empty(monkeypatch, tmp_store):
    """Model.request 返回空文本：回复无内容提示。"""
    prompt, sent = _stub_env(monkeypatch, tmp_store, model_text="")
    bot, event = _milky_group("zssm 空结果")
    await bot.handle_event(event)
    assert "模型没有返回内容" in str(sent[0][1])
