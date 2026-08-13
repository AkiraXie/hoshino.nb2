"""AI chat 插件与公共基建测试：纯函数、SQLite、行为路径。

行为测试 stub ``providers`` / ``rendering``，不连接真实模型或浏览器。
"""

from __future__ import annotations

import itertools
import pytest
from nonebot.adapters.milky import Bot as MilkyBot
from nonebot.adapters.milky.event import GroupMessageEvent as MilkyGroupMessageEvent
from nonebot.adapters.milky.model.api import MessageResponse
from pydantic_ai.usage import RunUsage

from hoshino.modules.ai.config import AIConfig, ProviderConfig, ProviderOptions

# 本文件会触发 uninfo 会话缓存，见 conftest 中 _clear_uninfo_cache 的说明。
pytestmark = pytest.mark.usefixtures("_clear_uninfo_cache")

# 每个事件用递增 message_seq，保证 alconna 的全局 unimsg_cache 键（按
# msg_id = f"{message_seq}@{scene}:{peer_id}"）不跨测试碰撞。起点取 200000，
# 高于仓库其他测试用到的所有硬编码 seq（1、7、1000/1001、7001、100000+），
# 避免同 (group, seq) 命中他人缓存的 UniMessage。
_seq = itertools.count(200000)


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
                "message_seq": next(_seq),
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


class FakeResult:
    def __init__(self, data: str, usage: RunUsage | None = None):
        self.data = data
        self.output = data  # AgentRunResult.output，与旧 .data 语义对齐
        self._messages: list = []
        self._usage = usage or RunUsage(input_tokens=5, output_tokens=3, requests=1)

    def all_messages(self):
        return self._messages

    def usage(self) -> RunUsage:
        return self._usage


class FakeAgentRun:
    """等价 pydantic-ai AgentRun：迭代产出一个 node，结束后 result 可用。"""

    def __init__(self, result: FakeResult, error: Exception | None = None):
        self._result = result
        self._error = error
        self.ctx = object()
        self.result: FakeResult | None = None
        self._count = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._error is not None:
            raise self._error
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
    def __init__(self, result: FakeResult, error: Exception | None = None):
        self._result = result
        self._error = error

    async def run(self, prompt, message_history=None):
        if self._error is not None:
            raise self._error
        self.prompt = prompt
        self.message_history = message_history
        return self._result

    def iter(
        self,
        prompt,
        *,
        message_history=None,
        deps=None,
        deferred_tool_results=None,
        conversation_id=None,
        output_type=None,
        capabilities=None,
    ):
        # 记录与 run 相同的信息，供断言。runner.run_agent 会透传
        # deferred_tool_results / conversation_id / output_type / capabilities。
        self.prompt = prompt
        self.message_history = message_history
        self.deps = deps
        self.deferred_tool_results = deferred_tool_results
        self.conversation_id = conversation_id
        self.output_type = output_type
        self.capabilities = capabilities
        return FakeAgentRun(self._result, self._error)


def _stub_config(monkeypatch, **overrides):
    from hoshino.modules.ai import chat

    defaults = dict(
        default="openai",
        system_prompt="你是测试助手。",
        max_history_messages=40,
        render_timeout_seconds=30.0,
        render_theme="light",
        providers={
            "openai": ProviderConfig(
                url="https://api.example.com/v1",
                key="sk-abcdefghij",
                config=ProviderOptions(kind="openai_chat", model="gpt-4o-mini"),
            ),
            "anthropic": ProviderConfig(
                url="https://api.anthropic.com",
                key="sk-ant-1234567890",
                config=ProviderOptions(kind="anthropic", model="claude-3-5-sonnet"),
            ),
        },
    )
    defaults.update(overrides)
    config = AIConfig(**defaults)
    monkeypatch.setattr(chat, "get_config", lambda: config)
    return config


def _stub_send(monkeypatch):
    sent: list[tuple[int, object]] = []

    async def fake_send_group_message(self, *, group_id: int, message):
        sent.append((group_id, message))
        return MessageResponse(message_seq=8, time=1)

    monkeypatch.setattr(MilkyBot, "send_group_message", fake_send_group_message)
    return sent


# ---------------------------------------------------------- 配置纯函数


def test_ai_config_defaults_and_lookup():
    config = AIConfig()
    assert config.default == ""
    assert config.max_history_messages == 40
    assert not config.has_provider("nope")
    assert config.get_provider("nope") is None

    config = AIConfig(
        providers={
            "p": ProviderConfig(
                url="u", key="k", config=ProviderOptions(kind="openai_chat")
            )
        }
    )
    assert config.has_provider("p")
    assert config.get_provider("p").key == "k"


def test_mask_key_and_url():
    from hoshino.modules.ai.config import mask_key, mask_url

    assert mask_key("") == ""
    assert mask_key("sk-1234567890") == "sk-1...7890"
    assert mask_key("short") == "*****"
    assert mask_url("https://api.example.com/v1") == "https://api.example.com/v1"
    assert "secret" not in mask_url("https://x.com/path?secret=abc")


def test_httpx_proxy_normalizes_socks():
    from hoshino.modules.ai.providers import _httpx_proxy

    assert _httpx_proxy(None) is None
    assert _httpx_proxy("http://127.0.0.1:7890") == "http://127.0.0.1:7890"
    assert _httpx_proxy("socks://127.0.0.1:7890") == "socks5://127.0.0.1:7890"
    assert _httpx_proxy("socks5://127.0.0.1:7890") == "socks5://127.0.0.1:7890"


def test_build_model_ignores_env_proxy(monkeypatch):
    """AIConfig.proxy 为空时应走 trust_env=False，读入 socks:// 环境变量也不崩。

    本用例在进程内设置 ALL_PROXY=socks://…（此前会令 httpx 构造 client 直接抛
    ValueError），验证 build_model 仍能成功创建 model。
    """
    import asyncio

    from hoshino.modules.ai.providers import build_model

    monkeypatch.setenv("ALL_PROXY", "socks://127.0.0.1:7890")
    monkeypatch.setenv("all_proxy", "socks://127.0.0.1:7890")
    monkeypatch.setenv("HTTPS_PROXY", "socks://127.0.0.1:7890")
    pc = ProviderConfig(
        url="https://api.example.com/v1",
        key="sk-test-key",
        config=ProviderOptions(kind="openai_chat", model="gpt-4o-mini"),
    )
    model = build_model(pc)  # proxy 缺省 None → trust_env=False，不读环境变量
    assert model is not None
    # 关闭 build_model 内部创建的 client（同步测试中 clear_agent_cache 不会
    # 找到事件循环，这里手动关闭避免 Unclosed client 告警）。
    from hoshino.modules.ai.providers import _http_clients

    for client in _http_clients:
        asyncio.run(client.aclose())
    _http_clients.clear()


# ------------------------------------------------------- provider 解析


def test_resolve_provider_scope_overrides_default(tmp_store):
    from hoshino.modules.ai.base import resolve_provider

    config = _make_provider_config(default="openai")
    tmp_store.set_scope_provider("milky:123", "anthropic")
    assert resolve_provider("milky:123", config) == "anthropic"
    assert resolve_provider("milky:999", config) == "openai"


def test_resolve_provider_invalid_scope_falls_back(tmp_store):
    from hoshino.modules.ai.base import resolve_provider

    config = _make_provider_config(default="openai")
    # 绑定不存在的 provider → 回退默认
    tmp_store.set_scope_provider("milky:123", "ghost")
    assert resolve_provider("milky:123", config) == "openai"


def test_resolve_provider_none_when_missing(tmp_store):
    from hoshino.modules.ai.base import resolve_provider

    config = _make_provider_config(default="")
    assert resolve_provider("milky:123", config) is None
    assert resolve_provider(None, config) is None


def _make_provider_config(default: str = "openai") -> AIConfig:
    return AIConfig(
        default=default,
        providers={
            "openai": ProviderConfig(
                url="u", key="k", config=ProviderOptions(kind="openai_chat")
            ),
            "anthropic": ProviderConfig(
                url="u2", key="k2", config=ProviderOptions(kind="anthropic")
            ),
        },
    )


# ------------------------------------------------------- 历史裁剪


def test_truncate_messages_by_turns():
    from hoshino.modules.ai.context import truncate_messages

    messages = [f"m{i}" for i in range(10)]  # type: ignore[list-item]
    assert truncate_messages(messages, 3) == ["m7", "m8", "m9"]
    assert truncate_messages(messages, 0) == messages
    assert truncate_messages(messages, 100) == messages


def test_serialize_roundtrip_empty():
    from hoshino.modules.ai.context import deserialize_messages, serialize_messages

    raw = serialize_messages([])
    assert deserialize_messages(raw) == []
    assert deserialize_messages(None) == []
    assert deserialize_messages("not-json") == []


# ------------------------------------------------------- 指标聚合


def test_snapshot_from_usage():
    from hoshino.modules.ai.metrics import snapshot_from_usage

    usage = RunUsage(
        input_tokens=10,
        output_tokens=4,
        cache_read_tokens=6,
        cache_write_tokens=2,
        requests=1,
    )
    snap = snapshot_from_usage(usage)
    assert snap.request_tokens == 10
    assert snap.response_tokens == 4
    assert snap.total_tokens == 14
    assert snap.cache_read_tokens == 6

    empty = snapshot_from_usage(None)
    assert empty.total_tokens == 0


def test_cache_hit_ratio():
    from hoshino.modules.ai.metrics import cache_hit_ratio

    assert cache_hit_ratio(10, 40) == 0.8
    assert cache_hit_ratio(0, 0) == 0.0


def test_format_stats_contains_tokens():
    from hoshino.modules.ai.metrics import format_stats

    text = format_stats(
        {
            "events": 3,
            "success_count": 2,
            "error_count": 1,
            "request_tokens": 10,
            "response_tokens": 5,
            "total_tokens": 15,
            "cache_read_tokens": 10,
            "cache_write_tokens": 2,
            "cache_hit_ratio": 0.5,
            "avg_latency_ms": 100.0,
        },
        provider_id="openai",
    )
    assert "openai" in text
    assert "命中率" in text
    assert "10" in text


# ------------------------------------------------------- 渲染纯函数


def test_markdown_to_html_supports_gfm():
    from hoshino.modules.ai.rendering import markdown_to_html

    html = markdown_to_html("# 标题\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\n- [x] done\n")
    assert "<h1>标题</h1>" in html
    assert "<table>" in html
    assert "task-list-item" in html


def test_markdown_to_html_highlights_code():
    from hoshino.modules.ai.rendering import markdown_to_html

    html = markdown_to_html("```python\nprint(1)\n```")
    assert "codehilite" in html
    assert "<span" in html


def test_build_full_html_themes():
    from hoshino.modules.ai.rendering import build_full_html

    body = "<p>hi</p>"
    assert "--bg: #ffffff" in build_full_html(body, "light")
    assert "--bg: #1f2328" in build_full_html(body, "dark")
    assert "--bg: #ffffff" in build_full_html(body, "unknown")  # 回退 light


# ------------------------------------------------------- SQLite store


def test_store_session_crud(tmp_store):
    tmp_store.save_session_messages("milky:1", '[{"id":1}]', "openai")
    assert tmp_store.load_session_messages("milky:1") == '[{"id":1}]'
    assert tmp_store.get_session_provider("milky:1") == "openai"

    tmp_store.save_session_messages("milky:1", "[]", "anthropic")
    assert tmp_store.load_session_messages("milky:1") == "[]"

    assert tmp_store.clear_session("milky:1") is True
    assert tmp_store.load_session_messages("milky:1") is None
    assert tmp_store.clear_session("milky:1") is False


def test_store_scope_provider_crud(tmp_store):
    assert tmp_store.get_scope_provider("milky:1") is None
    tmp_store.set_scope_provider("milky:1", "openai", updated_by="u1")
    assert tmp_store.get_scope_provider("milky:1") == "openai"
    tmp_store.set_scope_provider("milky:1", "anthropic", updated_by="u2")
    assert tmp_store.get_scope_provider("milky:1") == "anthropic"
    assert tmp_store.clear_scope_provider("milky:1") is True
    assert tmp_store.get_scope_provider("milky:1") is None


def test_store_clear_provider_references(tmp_store):
    tmp_store.set_scope_provider("milky:1", "openai")
    tmp_store.set_scope_provider("milky:2", "openai")
    tmp_store.set_scope_provider("milky:3", "anthropic")
    assert tmp_store.clear_provider_references("openai") == 2
    assert tmp_store.get_scope_provider("milky:1") is None
    assert tmp_store.get_scope_provider("milky:3") == "anthropic"


def test_store_usage_aggregate(tmp_store):
    tmp_store.record_usage_event(
        provider_id="openai",
        scope_key="milky:1",
        model="gpt-4o",
        request_tokens=10,
        response_tokens=5,
        cache_read_tokens=30,
        latency_ms=100.0,
    )
    tmp_store.record_usage_event(
        provider_id="openai",
        scope_key="milky:1",
        model="gpt-4o",
        request_tokens=10,
        response_tokens=0,
        latency_ms=50.0,
        error="timeout",
    )
    agg = tmp_store.aggregate_usage(provider_id="openai")
    assert agg["events"] == 2
    assert agg["request_tokens"] == 20
    assert agg["response_tokens"] == 5
    assert agg["cache_read_tokens"] == 30
    assert agg["success_count"] == 1
    assert agg["error_count"] == 1
    assert agg["avg_latency_ms"] == 75.0
    # 命中率 = 30 / (30 + 20) = 0.6
    assert agg["cache_hit_ratio"] == pytest.approx(0.6)

    filtered = tmp_store.aggregate_usage(provider_id="anthropic")
    assert filtered["events"] == 0


# ------------------------------------------------------- chat 行为


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_chat_hash_strips_prefix_and_sends_image(monkeypatch, tmp_store):
    from hoshino.modules.ai import chat

    _stub_config(monkeypatch)
    agent = FakeAgent(FakeResult("**你好**"))
    monkeypatch.setattr(chat.providers, "build_agent", lambda *a, **k: agent)

    async def fake_render(md, cfg):
        return b"FAKEPNG"

    monkeypatch.setattr(chat.rendering, "render_markdown", fake_render)
    monkeypatch.setattr(chat.sv, "check_enabled", lambda scope: True)
    sent = _stub_send(monkeypatch)

    bot, event = _milky_group("#你好", user_id=7)
    await bot.handle_event(event)

    assert agent.prompt == "你好"
    assert len(sent) == 1
    group_id, message = sent[0]
    assert group_id == 123456
    assert [segment.type for segment in message] == ["image"]


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_chat_empty_hash_no_call(monkeypatch, tmp_store):
    from hoshino.modules.ai import chat

    _stub_config(monkeypatch)
    agent = FakeAgent(FakeResult("x"))
    monkeypatch.setattr(chat.providers, "build_agent", lambda *a, **k: agent)
    monkeypatch.setattr(chat.sv, "check_enabled", lambda scope: True)
    sent = _stub_send(monkeypatch)

    bot, event = _milky_group("#   ", user_id=7)
    await bot.handle_event(event)

    assert sent == []


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_chat_without_hash_does_not_trigger(monkeypatch, tmp_store):
    from hoshino.modules.ai import chat

    _stub_config(monkeypatch)
    agent = FakeAgent(FakeResult("x"))
    monkeypatch.setattr(chat.providers, "build_agent", lambda *a, **k: agent)
    monkeypatch.setattr(chat.sv, "check_enabled", lambda scope: True)
    sent = _stub_send(monkeypatch)

    bot, event = _milky_group("普通消息", user_id=7)
    await bot.handle_event(event)

    assert sent == []


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_chat_no_provider_configured(monkeypatch, tmp_store):
    from hoshino.modules.ai import chat

    _stub_config(monkeypatch, default="", providers={})
    monkeypatch.setattr(chat.sv, "check_enabled", lambda scope: True)
    sent = _stub_send(monkeypatch)

    bot, event = _milky_group("#你好", user_id=7)
    await bot.handle_event(event)

    assert len(sent) == 1
    _, message = sent[0]
    assert "未配置任何 provider" in message.extract_plain_text()


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_chat_agent_error_records_metric(monkeypatch, tmp_store):
    from hoshino.modules.ai import chat

    _stub_config(monkeypatch)
    agent = FakeAgent(FakeResult("x"), error=RuntimeError("boom"))
    monkeypatch.setattr(chat.providers, "build_agent", lambda *a, **k: agent)
    monkeypatch.setattr(chat.sv, "check_enabled", lambda scope: True)
    sent = _stub_send(monkeypatch)

    bot, event = _milky_group("#你好", user_id=7)
    await bot.handle_event(event)

    assert len(sent) == 1
    _, message = sent[0]
    assert "AI 请求失败" in message.extract_plain_text()
    agg = tmp_store.aggregate_usage(provider_id="openai")
    assert agg["error_count"] == 1


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_chat_render_failure_falls_back_to_text(monkeypatch, tmp_store):
    from hoshino.modules.ai import chat

    _stub_config(monkeypatch)
    agent = FakeAgent(FakeResult("**你好**"))
    monkeypatch.setattr(chat.providers, "build_agent", lambda *a, **k: agent)

    async def broken_render(md, cfg):
        raise TimeoutError("browser timeout")

    monkeypatch.setattr(chat.rendering, "render_markdown", broken_render)
    monkeypatch.setattr(chat.sv, "check_enabled", lambda scope: True)
    sent = _stub_send(monkeypatch)

    bot, event = _milky_group("#你好", user_id=7)
    await bot.handle_event(event)

    assert len(sent) == 1
    _, message = sent[0]
    assert message.extract_plain_text() == "**你好**"


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_chat_scope_provider_overrides_default(monkeypatch, tmp_store):
    from hoshino.modules.ai import chat

    config = _stub_config(monkeypatch)
    # 该群 scope 绑定 anthropic → build_agent 应收到 anthropic
    tmp_store.set_scope_provider("milky:123456", "anthropic")
    captured: dict = {}

    def fake_build(provider_id, provider_config, *, proxy=None):
        captured["provider_id"] = provider_id
        captured["provider_config"] = provider_config
        captured["proxy"] = proxy
        return FakeAgent(FakeResult("hi"))

    monkeypatch.setattr(chat.providers, "build_agent", fake_build)
    monkeypatch.setattr(chat.sv, "check_enabled", lambda scope: True)
    sent = _stub_send(monkeypatch)

    bot, event = _milky_group("#hi", user_id=7)
    await bot.handle_event(event)

    assert captured["provider_id"] == "anthropic"
    assert captured["provider_config"] is config.get_provider("anthropic")
    assert captured["proxy"] == config.proxy
    assert len(sent) == 1
