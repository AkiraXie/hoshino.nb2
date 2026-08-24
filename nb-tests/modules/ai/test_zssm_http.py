"""zssm 完整链路集成测试：真实 build_model + 本地 fake HTTP 服务器。

与 test_zssm.py 的 stub 策略互补——那里 stub _build_zssm_agent 验证行为路径；
这里不 stub，让 zssm 事件真正经 _build_zssm_agent 向 fake_ai_server 发出 HTTP
请求，验证"zssm → Agent（含 web 工具注入）→ 模型 JSON → 解析回复"整条链路。
渲染与发消息仍 stub（不依赖 playwright / 真实协议）。
"""

from __future__ import annotations

import pytest
from nonebot.adapters.milky import Bot as MilkyBot
from nonebot.adapters.milky.config import ClientInfo
from nonebot.adapters.milky.event import GroupMessageEvent as MilkyGroupMessageEvent
from nonebot.adapters.milky.model.api import MessageResponse

from _helpers import next_seq
from hoshino.ai.config import AIConfig

# _clear_uninfo_cache 和 _fresh_conversation_manager 由 modules/ai/conftest.py 提供。

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
def _fresh_agent_cache(monkeypatch):
    """每个测试独立 zssm Agent 缓存：模块级缓存会跨测试残留。"""
    from hoshino.modules.ai import zssm

    monkeypatch.setattr(zssm, "_agent_cache", {})


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
    """provider 指向 fake server；stub 渲染/发送，不 stub agent 构建。"""
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
    """完整链路：事件 → Agent（真实 HTTP）→ JSON 解析 → 回复。"""
    base_url, requests = fake_ai_server
    sent = _stub_http_env(monkeypatch, tmp_store, base_url)

    bot, event = _milky_group("zssm 显卡是什么 --text")
    await bot.handle_event(event)

    assert "这是显卡解释" in sent[0][1].extract_plain_text()
    assert len(requests) >= 1
    req = requests[0]
    assert req["stem"].endswith("/chat/completions")
    assert req["body"]["model"] == "gpt-4o-mini"


@pytest.mark.usefixtures("_nonebot_bootstrap")
@pytest.mark.parametrize("fake_ai_server", [_ZSSM_JSON_RESPONSE], indirect=True)
async def test_zssm_http_injects_web_tools(fake_ai_server, monkeypatch, tmp_store):
    """zssm Agent 应只注入 web 类别工具：web_search / web_fetch / browser_use。"""
    base_url, requests = fake_ai_server
    _stub_http_env(monkeypatch, tmp_store, base_url)

    bot, event = _milky_group("zssm 显卡是什么 --text")
    await bot.handle_event(event)

    assert len(requests) >= 1
    tools = requests[0]["body"].get("tools") or []
    names = {tool.get("function", {}).get("name", "") for tool in tools}
    assert {"web_search", "web_fetch", "browser_use"} <= names
    # 不应注入其他类别工具（core / computer / bot / skill）
    for forbidden in ("memory", "now", "bash", "python", "file", "send_message", "skill_read"):
        assert forbidden not in names
