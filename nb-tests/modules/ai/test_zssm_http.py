"""zssm 完整链路集成测试：真实 build_model + 本地 fake HTTP 服务器。

与 test_zssm.py 的 stub 策略互补——那里 stub _request_explain 验证行为路径；
这里不 stub，让 zssm 事件真正经 Model.request 向 fake_ai_server 发出 HTTP
请求，验证"zssm → Model.request → JSON → 解析回复"整条链路。
发消息仍 stub（不依赖真实协议）。
"""

from __future__ import annotations

import pytest
from nonebot.adapters.milky import Bot as MilkyBot
from nonebot.adapters.milky.config import ClientInfo
from nonebot.adapters.milky.event import GroupMessageEvent as MilkyGroupMessageEvent
from nonebot.adapters.milky.model.api import MessageResponse

from _helpers import next_seq
from hoshino.ai.config import AIConfig

_ZSSM_JSON_RESPONSE = {
    "id": "chatcmpl-zssm",
    "object": "chat.completion",
    "created": 1677652288,
    "model": "gpt-4o-mini",
    "choices": [
        {
            "index": 0,
            "message": {
                "role": "assistant",
                "content": '{"output":"这是显卡解释","keywords":["显卡"],"blocked":false}',
            },
            "finish_reason": "stop",
        }
    ],
    "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
}


@pytest.fixture(autouse=True)
def _fresh_model_cache(monkeypatch):
    """每个测试独立 zssm model 缓存：模块级缓存会跨测试残留。"""
    from hoshino.modules.ai import zssm

    monkeypatch.setattr(zssm, "_model_cache", {})


def _milky_group(text: str, *, user_id: int = 42, role: str = "member", group_id: int = 123456):
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
        }
    )
    assert isinstance(event, MilkyGroupMessageEvent)
    event.to_me = False
    return bot, event


def _stub_http_env(monkeypatch, tmp_store, base_url: str):
    """provider 指向 fake server；stub 发送，不 stub model 构建。"""
    from hoshino.modules.ai import zssm

    monkeypatch.setattr(zssm.sv, "check_enabled", lambda scope: True)
    config = AIConfig(default="openai")
    monkeypatch.setattr(zssm, "get_config", lambda: config)

    tmp_store.upsert_provider_row(
        provider_id="openai",
        url=base_url,
        key="sk-test-zssm",
        kind="openai_chat",
        default_text_model="gpt-4o-mini",
    )
    tmp_store.upsert_provider_model("openai", "gpt-4o-mini", "text")

    sent: list[tuple[int, object]] = []

    async def fake_send_group_message(self, *, group_id: int, message):
        sent.append((group_id, message))
        return MessageResponse(message_seq=8, time=1)

    monkeypatch.setattr(MilkyBot, "send_group_message", fake_send_group_message)
    return sent


@pytest.mark.usefixtures("_nonebot_bootstrap")
@pytest.mark.parametrize("fake_ai_server", [_ZSSM_JSON_RESPONSE], indirect=True)
async def test_zssm_http_full_chain(fake_ai_server, monkeypatch, tmp_store):
    """完整链路：事件 → Model.request（真实 HTTP）→ JSON 解析 → 转发回复。"""
    base_url, requests = fake_ai_server
    sent = _stub_http_env(monkeypatch, tmp_store, base_url)

    bot, event = _milky_group("zssm 显卡是什么")
    await bot.handle_event(event)

    all_text = " ".join(str(s[1]) for s in sent)
    assert "这是显卡解释" in all_text
    assert len(requests) >= 1
    req = requests[0]
    assert req["stem"].endswith("/chat/completions")
    assert req["body"]["model"] == "gpt-4o-mini"


@pytest.mark.usefixtures("_nonebot_bootstrap")
@pytest.mark.parametrize("fake_ai_server", [_ZSSM_JSON_RESPONSE], indirect=True)
async def test_zssm_http_no_tools_in_request(fake_ai_server, monkeypatch, tmp_store):
    """zssm Model.request 不应携带工具定义（纯文本子请求）。"""
    base_url, requests = fake_ai_server
    _stub_http_env(monkeypatch, tmp_store, base_url)

    bot, event = _milky_group("zssm 显卡是什么")
    await bot.handle_event(event)

    assert len(requests) >= 1
    tools = requests[0]["body"].get("tools")
    # Model.request 不带工具，tools 应为 None 或空
    assert not tools
