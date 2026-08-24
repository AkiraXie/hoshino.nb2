"""chat 插件完整链路集成测试：真实 ``build_agent`` + 本地 fake HTTP 服务器。

与 test_ai_chat.py 的 stub 策略互补：那里 stub ``build_agent`` 验证行为路径；这里不 stub
provider，让 ``#你好`` 事件真正经 ``build_agent`` 向 ``fake_ai_server`` 发出 HTTP 请求并解析
响应，验证"发一句话 → aichat"在修复 ``ApprovalRequiredToolset`` 后整条链路可用。渲染与
发消息仍 stub（不依赖 playwright / 真实协议）。
"""

from __future__ import annotations

import pytest
from nonebot.adapters.milky import Bot as MilkyBot
from nonebot.adapters.milky.event import GroupMessageEvent as MilkyGroupMessageEvent
from nonebot.adapters.milky.model.api import MessageResponse

from _helpers import next_seq
from hoshino.ai.config import AIConfig

# _clear_uninfo_cache 由 modules/ai/conftest.py 提供。


def _milky_group(
    text: str,
    *,
    user_id: int = 42,
    role: str = "admin",
    group_id: int = 123456,
) -> tuple[MilkyBot, MilkyGroupMessageEvent]:
    from nonebot import get_adapters
    from nonebot.adapters.milky import Adapter as MilkyAdapter
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
    assert isinstance(event, MilkyGroupMessageEvent)
    event.to_me = False
    return bot, event


def _stub_send(monkeypatch):
    sent: list[tuple[int, object]] = []

    async def fake_send_group_message(self, *, group_id: int, message):
        sent.append((group_id, message))
        return MessageResponse(message_seq=8, time=1)

    monkeypatch.setattr(MilkyBot, "send_group_message", fake_send_group_message)
    return sent


def _seed_openai(tmp_store, base_url: str, *, bad_path: bool = False) -> AIConfig:
    """预置 openai provider 行（url 指向 fake server），返回默认配置。"""
    url = f"{base_url}/nope" if bad_path else base_url
    tmp_store.upsert_provider_row(
        provider_id="openai",
        url=url,
        key="sk-test-openai",
        kind="openai_chat",
        default_text_model="gpt-4o-mini",
    )
    tmp_store.upsert_provider_model("openai", "gpt-4o-mini", "text")
    return AIConfig(default="openai", system_prompt="你是测试助手。")


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_chat_full_http_roundtrip(fake_ai_server, monkeypatch, tmp_store):
    """#你好 → 真实 build_agent 发 HTTP 到 fake server → 渲染图片发送，不报错。"""
    base_url, requests = fake_ai_server
    from hoshino.modules.ai import chat

    monkeypatch.setattr(chat, "get_config", lambda: _seed_openai(tmp_store, base_url))
    monkeypatch.setattr(chat.sv, "check_enabled", lambda scope: True)

    async def fake_render(md, cfg):
        return b"FAKEPNG"

    monkeypatch.setattr(chat.rendering, "render_markdown", fake_render)
    sent = _stub_send(monkeypatch)

    bot, event = _milky_group("#你好", user_id=7)
    await bot.handle_event(event)

    # 真实 HTTP 请求确实到达 fake 服务器，路径/鉴权/body 正确
    assert len(requests) == 1, "chat 链路应产生一次 provider HTTP 请求"
    req = requests[0]
    assert req["stem"].endswith("/chat/completions")
    assert req["headers"]["authorization"] == "Bearer sk-test-openai"
    assert req["body"]["model"] == "gpt-4o-mini"

    # 渲染成功 → 以图片形式发送
    assert len(sent) == 1
    _, message = sent[0]
    assert [seg.type for seg in message] == ["image"]


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_chat_http_agent_error_falls_back_to_text(fake_ai_server, monkeypatch, tmp_store):
    """fake server 返回 404（模拟 provider 异常）→ chat 回复失败提示而不是崩溃。"""
    base_url, requests = fake_ai_server
    from hoshino.modules.ai import chat

    # 指向不存在的路径：openai SDK 会把 base_url 拼成 /nope/chat/completions，
    # fake 服务器对未知路径返回 404，SDK 解析成错误 → chat 捕获并回复失败提示。
    monkeypatch.setattr(
        chat, "get_config", lambda: _seed_openai(tmp_store, base_url, bad_path=True)
    )
    monkeypatch.setattr(chat.sv, "check_enabled", lambda scope: True)
    sent = _stub_send(monkeypatch)

    bot, event = _milky_group("#你好", user_id=7)
    await bot.handle_event(event)

    assert len(sent) == 1
    _, message = sent[0]
    assert "AI 请求失败" in message.extract_plain_text()


_EMPTY_FUNCTION_CALL_RESPONSE = {
    "id": "chatcmpl-fake",
    "object": "chat.completion",
    "created": 1677652288,
    "model": "deepseek-v4-flash",
    "choices": [
        {
            "index": 0,
            "message": {
                "role": "assistant",
                "content": "好的！给你推荐几个不用开火就能搞定的选择～",
                "function_call": {"name": None, "arguments": None},
            },
            "finish_reason": "stop",
        }
    ],
    "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
}


@pytest.mark.usefixtures("_nonebot_bootstrap")
@pytest.mark.parametrize("fake_ai_server", [_EMPTY_FUNCTION_CALL_RESPONSE], indirect=True)
async def test_chat_http_empty_function_call_placeholder_succeeds(
    fake_ai_server, monkeypatch, tmp_store
):
    """网关附加空 function_call 占位（name/arguments 为 null）→ chat 正常回复。

    复现 opencode-go 网关真实形态：内容正常但每条响应都带
    ``function_call: {name: null, arguments: null}``。归一化占位后校验通过，
    chat 应成功渲染并发送图片回复，而不是 UnexpectedModelBehavior 失败。
    """
    base_url, requests = fake_ai_server
    from hoshino.modules.ai import chat

    monkeypatch.setattr(chat, "get_config", lambda: _seed_openai(tmp_store, base_url))
    monkeypatch.setattr(chat.sv, "check_enabled", lambda scope: True)

    async def fake_render(md, cfg):
        return b"FAKEPNG"

    monkeypatch.setattr(chat.rendering, "render_markdown", fake_render)
    sent = _stub_send(monkeypatch)

    bot, event = _milky_group("#你好", user_id=7)
    await bot.handle_event(event)

    assert len(requests) == 1
    assert len(sent) == 1
    _, message = sent[0]
    assert [seg.type for seg in message] == ["image"]
