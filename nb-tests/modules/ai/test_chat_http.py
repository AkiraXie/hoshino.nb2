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
from fake_ai_server import openai_text_response, set_chat_responses
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
    )
    tmp_store.set_global_value("default_model_provider", "openai")
    tmp_store.set_global_value("default_model", "gpt-4o-mini")
    return AIConfig(default="openai", system_prompt="你是测试助手。")


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_chat_full_http_roundtrip(fake_ai_server, monkeypatch, tmp_store):
    """#你好 → 真实 build_agent 发 HTTP 到 fake server → 渲染图片发送，不报错。"""
    base_url, requests = fake_ai_server
    from hoshino.modules.ai import chat

    monkeypatch.setattr(chat, "get_config", lambda: _seed_openai(tmp_store, base_url))
    monkeypatch.setattr(chat.sv, "check_enabled", lambda scope: True)
    sent = _stub_send(monkeypatch)
    # 回复带 Markdown 结构 → 形态判定为图片（纯文字回复走纯文本消息，见 test_ai_chat.py）。
    set_chat_responses([openai_text_response("## 你好\n\n- 一\n- 二")])

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
async def test_chat_http_plain_short_reply_sends_single_message(
    fake_ai_server, monkeypatch, tmp_store
):
    """聊天场景：简短纯文本回复 → 单条普通消息（不是合并转发）。"""
    base_url, requests = fake_ai_server
    from hoshino.modules.ai import chat

    monkeypatch.setattr(chat, "get_config", lambda: _seed_openai(tmp_store, base_url))
    monkeypatch.setattr(chat.sv, "check_enabled", lambda scope: True)
    sent = _stub_send(monkeypatch)
    content = "早啊，今天也要加油哦，记得吃早饭。"
    set_chat_responses([openai_text_response(content)])

    bot, event = _milky_group("#早", user_id=7)
    await bot.handle_event(event)

    assert len(requests) == 1
    assert len(sent) == 1
    _, message = sent[0]
    assert [seg.type for seg in message] == ["text"]
    assert message.extract_plain_text() == content


# 讲内容场景的长纯文本：无 Markdown/排版记号，三段 >210 字 → 必触发分段。
_LONG_PLAIN_REPLY = (
    "TCP 三次握手要解决的核心问题是双方都要确认彼此的收发能力，同时协商好初始序列号，"
    "防止网络里滞留的旧连接请求突然送达，让服务端白白开出资源。"
    "第一次握手客户端发出 SYN，服务端由此知道客户端能发、自己能收。"
    "\n\n"
    "第二次握手服务端回 SYN 加 ACK，客户端收到后就确认了双方收发都正常，"
    "但服务端此时还不能确定客户端是否真的收到了自己的应答。"
    "第三次握手客户端再回一个 ACK，服务端这才确认自己能发、对方能收，连接正式建立。"
    "\n\n"
    "如果只有两次握手，服务端无法确认应答是否送达，失效的历史连接请求一到就会浪费资源。"
    "所以三次不是玄学，而是在不可靠网络上达成双方收发能力共识所需的最小次数，两次不够，四次多余。"
)


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_chat_http_long_plain_reply_bundles_forward_record(
    fake_ai_server, monkeypatch, tmp_store
):
    """讲内容场景：长纯文本回复分段后整合成一条合并转发聊天记录（不逐条刷）。"""
    base_url, requests = fake_ai_server
    from hoshino.ai import reply
    from hoshino.modules.ai import chat

    monkeypatch.setattr(chat, "get_config", lambda: _seed_openai(tmp_store, base_url))
    monkeypatch.setattr(chat.sv, "check_enabled", lambda scope: True)
    sent = _stub_send(monkeypatch)
    set_chat_responses([openai_text_response(_LONG_PLAIN_REPLY)])

    bot, event = _milky_group("#讲讲三次握手", user_id=7)
    await bot.handle_event(event)

    assert len(requests) == 1
    expected = reply.split_plain_text(_LONG_PLAIN_REPLY)
    assert len(expected) >= 2, "探针文本必须够长以触发分段"
    # 一次 API 调用、一条合并转发记录，节点正文即各分段
    assert len(sent) == 1
    _, message = sent[0]
    assert len(message) == 1
    forward = message[0]
    assert forward.type == "forward"
    nodes = forward.data["messages"]
    assert [node.segments.extract_plain_text() for node in nodes] == expected


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
                "content": "## 推荐\n\n- 不开火的选择一\n- 不开火的选择二",
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
    sent = _stub_send(monkeypatch)

    bot, event = _milky_group("#你好", user_id=7)
    await bot.handle_event(event)

    assert len(requests) == 1
    assert len(sent) == 1
    _, message = sent[0]
    assert [seg.type for seg in message] == ["image"]
