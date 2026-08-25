"""zssm 完整链路集成测试：真实 build_model + 本地 fake HTTP 服务器。

与 test_zssm.py 的 stub 策略互补——那里 stub _build_zssm_agent 验证行为路径；
这里不 stub，让 zssm 事件真正经 Agent 向 fake_ai_server 发出 HTTP
请求，验证"zssm → Agent（含 web 工具 + ZssmOutput）→ 结构化输出 → 回复"整条链路。
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

# Fake server 返回合法 JSON 以通过 ZssmOutput 校验。
# pydantic-ai 使用 response_format / tool_call 强制结构化输出，
# 但 fake server 只返回纯文本 content，Agent 会把它当 text output 处理。
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
    """provider 指向 fake server；stub 发送，不 stub agent 构建。"""
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
    """完整链路：事件 → Agent（真实 HTTP + ZssmOutput）→ 转发回复。"""
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
async def test_zssm_http_injects_web_tools(fake_ai_server, monkeypatch, tmp_store):
    """zssm Agent 应注入 web 类别工具。"""
    base_url, requests = fake_ai_server
    _stub_http_env(monkeypatch, tmp_store, base_url)

    bot, event = _milky_group("zssm 显卡是什么")
    await bot.handle_event(event)

    assert len(requests) >= 1
    tools = requests[0]["body"].get("tools") or []
    names = {tool.get("function", {}).get("name", "") for tool in tools}
    # 至少有一个 web 工具被注入（具体取决于运行时哪些可用）
    web_tool_names = {"web_search", "web_fetch", "browser_use"}
    injected_web = names & web_tool_names
    assert injected_web, f"未注入任何 web 工具，实际 tools: {names}"
