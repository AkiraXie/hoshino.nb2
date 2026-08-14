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

from hoshino.ai.config import AIConfig

# 本文件会触发 uninfo 会话缓存，见 conftest 中 _clear_uninfo_cache 的说明。
pytestmark = pytest.mark.usefixtures("_clear_uninfo_cache")

# 每个事件用递增 message_seq，保证 alconna 的全局 unimsg_cache 键（按
# msg_id = f"{message_seq}@{scene}:{peer_id}"）不跨测试碰撞。起点取 200000，
# 高于仓库其他测试用到的所有硬编码 seq（1、7、1000/1001、7001、100000+），
# 避免同 (group, seq) 命中他人缓存的 UniMessage。
_seq = itertools.count(200000)


@pytest.fixture(autouse=True)
def _fresh_conversation_manager(monkeypatch):
    """每个测试独立 ConversationManager：单例内存缓存会跨测试残留。"""
    from hoshino.ai import sessions

    manager = sessions.ConversationManager()
    monkeypatch.setattr(sessions, "conversation_manager", manager)
    return manager


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
    def __init__(
        self,
        data: str,
        usage: RunUsage | None = None,
        messages: list | None = None,
        prefix: list | None = None,
    ):
        self.data = data
        self.output = data  # AgentRunResult.output，与旧 .data 语义对齐
        self._messages: list = list(messages) if messages is not None else []
        self._prefix: list = list(prefix) if prefix is not None else []
        self._usage = usage or RunUsage(input_tokens=5, output_tokens=3, requests=1)

    def all_messages(self):
        # 对齐真实 pydantic-ai：all_messages = message_history + 新增。
        return [*self._prefix, *self._messages]

    def with_prefix(self, prefix: list) -> "FakeResult":
        """返回一个等价结果，其 all_messages 前置 message_history。"""
        return FakeResult(self.data, self._usage, self._messages, prefix)

    def usage(self) -> RunUsage:
        return self._usage


class FakeAgentRun:
    """等价 pydantic-ai AgentRun：迭代产出一个 node，结束后 result 可用。"""

    def __init__(
        self,
        result: FakeResult,
        error: Exception | None = None,
        message_history: list | None = None,
    ):
        self._result = result
        self._error = error
        self._message_history = list(message_history) if message_history else []
        self.ctx = object()
        self.result: FakeResult | None = None
        self._count = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._error is not None:
            raise self._error
        if self._count >= 1:
            self.result = self._result.with_prefix(self._message_history)
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
        usage_limits=None,
    ):
        # 记录与 run 相同的信息，供断言。runner.run_agent 会透传
        # deferred_tool_results / conversation_id / output_type / capabilities /
        # usage_limits。
        self.prompt = prompt
        self.message_history = message_history
        self.deps = deps
        self.deferred_tool_results = deferred_tool_results
        self.conversation_id = conversation_id
        self.output_type = output_type
        self.capabilities = capabilities
        self.usage_limits = usage_limits
        return FakeAgentRun(self._result, self._error, message_history)


class RetryAgent(FakeAgent):
    """第一次 iter 抛错、之后成功的替身：验证 request-error 有界重试。"""

    def __init__(self, error: Exception):
        super().__init__(FakeResult("回答"))
        self._first_error = error
        self._calls = 0

    def iter(self, prompt, **kwargs):
        self.prompt = prompt
        self.message_history = kwargs.get("message_history")
        self._calls += 1
        if self._calls == 1:
            return FakeAgentRun(
                FakeResult("x"), self._first_error, kwargs.get("message_history")
            )
        return FakeAgentRun(self._result, None, kwargs.get("message_history"))


class _RetryDeps:
    """run_agent_with_retry 构建 RequestErrorContext 所需的最小 deps 替身。"""

    scope_key = "milky:1"
    surface = "chat"

    class telemetry:
        provider_id = "openai"


@pytest.fixture
def _reset_hooks():
    """钩子注册表是模块全局，每个测试前后清空。"""
    from hoshino.ai import hooks

    hooks.reset_hooks()
    yield
    hooks.reset_hooks()


def _stub_config(monkeypatch, tmp_store, *, seed_providers: bool = True, **overrides):
    from hoshino.modules.ai import chat

    defaults = dict(
        default="openai",
        system_prompt="你是测试助手。",
        max_history_messages=40,
        render_timeout_seconds=30.0,
        render_theme="light",
    )
    defaults.update(overrides)
    config = AIConfig(**defaults)
    monkeypatch.setattr(chat, "get_config", lambda: config)
    if seed_providers:
        # provider 存 DB（唯一事实源）：预置两个 provider 及其 model-list。
        tmp_store.upsert_provider_row(
            provider_id="openai",
            url="https://api.example.com/v1",
            key="sk-abcdefghij",
            kind="openai_chat",
            default_text_model="gpt-4o-mini",
        )
        tmp_store.upsert_provider_model("openai", "gpt-4o-mini", "text")
        tmp_store.upsert_provider_row(
            provider_id="anthropic",
            url="https://api.anthropic.com",
            key="sk-ant-1234567890",
            kind="anthropic",
            default_text_model="claude-3-5-sonnet",
        )
        tmp_store.upsert_provider_model("anthropic", "claude-3-5-sonnet", "text")
    return config


def _stub_send(monkeypatch):
    sent: list[tuple[int, object]] = []

    async def fake_send_group_message(self, *, group_id: int, message):
        sent.append((group_id, message))
        return MessageResponse(message_seq=8, time=1)

    monkeypatch.setattr(MilkyBot, "send_group_message", fake_send_group_message)
    return sent


# ---------------------------------------------------------- 配置纯函数


def test_ai_config_defaults():
    config = AIConfig()
    assert config.default == ""
    assert config.max_history_messages == 64
    # 原生联网搜索与工具重试预算的默认值
    assert config.web_search_native is True
    assert config.tool_max_retries == 3
    # web_fetch 证书校验与渲染清晰度/emoji 默认值
    assert config.web_fetch_verify_ssl is False
    assert config.render_device_scale == 2.0
    assert config.render_emoji is True


def test_mask_key_and_url():
    from hoshino.ai.config import mask_key, mask_url

    assert mask_key("") == ""
    assert mask_key("sk-1234567890") == "sk-1...7890"
    assert mask_key("short") == "*****"
    assert mask_url("https://api.example.com/v1") == "https://api.example.com/v1"
    assert "secret" not in mask_url("https://x.com/path?secret=abc")


def test_httpx_proxy_normalizes_socks():
    from hoshino.ai.providers import _httpx_proxy

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

    from hoshino.ai.provider import ProviderRecord
    from hoshino.ai.providers import build_model

    monkeypatch.setenv("ALL_PROXY", "socks://127.0.0.1:7890")
    monkeypatch.setenv("all_proxy", "socks://127.0.0.1:7890")
    monkeypatch.setenv("HTTPS_PROXY", "socks://127.0.0.1:7890")
    record = ProviderRecord(
        id="openai",
        url="https://api.example.com/v1",
        key="sk-test-key",
        kind="openai_chat",
    )
    model = build_model(record, "gpt-4o-mini")  # proxy 缺省 None → trust_env=False
    assert model is not None
    # 关闭 build_model 内部创建的 client（同步测试中 clear_agent_cache 不会
    # 找到事件循环，这里手动关闭避免 Unclosed client 告警）。
    from hoshino.ai.providers import _http_clients

    for client in _http_clients:
        asyncio.run(client.aclose())
    _http_clients.clear()


# ------------------------------------------------------- provider 解析


def test_resolve_provider_scope_overrides_default(tmp_store):
    from hoshino.ai.base import resolve_provider

    config = _seed_test_providers(tmp_store)
    tmp_store.set_scope_provider("milky:123", "anthropic")
    assert resolve_provider("milky:123", config) == "anthropic"
    assert resolve_provider("milky:999", config) == "openai"


def test_resolve_provider_invalid_scope_falls_back(tmp_store):
    from hoshino.ai.base import resolve_provider

    config = _seed_test_providers(tmp_store)
    # 绑定不存在的 provider → 回退默认
    tmp_store.set_scope_provider("milky:123", "ghost")
    assert resolve_provider("milky:123", config) == "openai"


def test_resolve_provider_none_when_missing(tmp_store):
    from hoshino.ai.base import resolve_provider

    config = AIConfig(default="")
    assert resolve_provider("milky:123", config) is None
    assert resolve_provider(None, config) is None


def _seed_test_providers(tmp_store) -> AIConfig:
    """预置 openai/anthropic 两个 provider 行，返回默认指向 openai 的配置。"""
    tmp_store.upsert_provider_row(
        provider_id="openai",
        url="u",
        key="k",
        kind="openai_chat",
        default_text_model="gpt-4o-mini",
    )
    tmp_store.upsert_provider_row(
        provider_id="anthropic",
        url="u2",
        key="k2",
        kind="anthropic",
        default_text_model="claude-3-5-sonnet",
    )
    return AIConfig(default="openai")


# ------------------------------------------------------- 历史裁剪


def test_truncate_messages_by_turns():
    from hoshino.ai.context import truncate_messages

    messages = [f"m{i}" for i in range(10)]  # type: ignore[list-item]
    assert truncate_messages(messages, 3) == ["m7", "m8", "m9"]
    assert truncate_messages(messages, 0) == messages
    assert truncate_messages(messages, 100) == messages


def test_serialize_roundtrip_empty():
    from hoshino.ai.context import deserialize_messages, serialize_messages

    raw = serialize_messages([])
    assert deserialize_messages(raw) == []
    assert deserialize_messages(None) == []
    assert deserialize_messages("not-json") == []


# ------------------------------------------------------- 指标聚合


def test_snapshot_from_usage():
    from hoshino.ai.metrics import snapshot_from_usage

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
    from hoshino.ai.metrics import cache_hit_ratio

    assert cache_hit_ratio(10, 40) == 0.8
    assert cache_hit_ratio(0, 0) == 0.0


def test_format_stats_contains_tokens():
    from hoshino.ai.metrics import format_stats

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
    from hoshino.ai.rendering import markdown_to_html

    html = markdown_to_html("# 标题\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\n- [x] done\n")
    assert "<h1>标题</h1>" in html
    assert "<table>" in html
    assert "task-list-item" in html


def test_markdown_to_html_highlights_code():
    from hoshino.ai.rendering import markdown_to_html

    html = markdown_to_html("```python\nprint(1)\n```")
    assert "codehilite" in html
    assert "<span" in html


def test_build_full_html_themes():
    from hoshino.ai.rendering import build_full_html

    body = "<p>hi</p>"
    assert "--bg: #ffffff" in build_full_html(body, "light")
    assert "--bg: #1f2328" in build_full_html(body, "dark")
    assert "--bg: #ffffff" in build_full_html(body, "unknown")  # 回退 light
    # 彩色 emoji 字体默认开启，可关闭
    assert '"Apple Color Emoji"' in build_full_html(body, "light")
    assert '"Apple Color Emoji"' not in build_full_html(body, "light", emoji=False)
    # 强调色注入 CSS（彩色）
    assert "--accent: #0969da" in build_full_html(body, "light")


def test_build_full_html_uses_configured_font():
    from hoshino.ai.rendering import build_full_html

    body = "<p>hi</p>"
    # 默认 Inter；主字体带引号置于字体栈首位，中文经系统字体回退
    assert '"Inter"' in build_full_html(body, "light")
    assert '"JetBrains Mono"' in build_full_html(body, "light", font="JetBrains Mono")
    assert '"Inter"' not in build_full_html(body, "light", font="JetBrains Mono")


def test_build_full_html_spacing():
    """渲染 CSS 采用更宽松的行距与字距，避免正文拥挤。"""
    from hoshino.ai.rendering import build_full_html

    html = build_full_html("<p>hi</p>", "light")
    assert "line-height: 1.8" in html
    assert "letter-spacing: 0.02em" in html


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

    _stub_config(monkeypatch, tmp_store)
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

    _stub_config(monkeypatch, tmp_store)
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

    _stub_config(monkeypatch, tmp_store)
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

    _stub_config(monkeypatch, tmp_store, seed_providers=False, default="")
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

    _stub_config(monkeypatch, tmp_store)
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
async def test_chat_agent_error_logs_detail_and_tools(monkeypatch, tmp_store):
    """可观测性：失败日志包含异常详情（message/body）与失败前工具调用。"""
    from loguru import logger as loguru_logger
    from pydantic_ai.exceptions import UnexpectedModelBehavior

    from hoshino.modules.ai import chat

    _stub_config(monkeypatch, tmp_store)
    agent = FakeAgent(
        FakeResult("x"),
        error=UnexpectedModelBehavior(
            "模型返回了非法工具调用", body='{"tool": "web_search"}'
        ),
    )
    monkeypatch.setattr(chat.providers, "build_agent", lambda *a, **k: agent)
    monkeypatch.setattr(chat.sv, "check_enabled", lambda scope: True)
    sent = _stub_send(monkeypatch)

    records: list[str] = []
    sink_id = loguru_logger.add(records.append, format="{message}", level="DEBUG")
    try:
        bot, event = _milky_group("#你好", user_id=7)
        await bot.handle_event(event)
    finally:
        loguru_logger.remove(sink_id)

    joined = "\n".join(records)
    assert "error=UnexpectedModelBehavior" in joined
    assert "模型返回了非法工具调用" in joined  # message 字段可见
    assert '"tool": "web_search"' in joined  # body 字段可见
    assert "tools=-" in joined  # FakeAgent 无图节点 → 无工具调用

    # 用户侧回复保持简短，不把原始 body 泄进群聊
    _, message = sent[0]
    assert "web_search" not in message.extract_plain_text()


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_chat_render_failure_falls_back_to_text(monkeypatch, tmp_store):
    from hoshino.modules.ai import chat

    _stub_config(monkeypatch, tmp_store)
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

    _stub_config(monkeypatch, tmp_store)
    # 该群 scope 绑定 anthropic → build_agent 应收到 anthropic 及其默认模型
    tmp_store.set_scope_provider("milky:123456", "anthropic")
    captured: dict = {}

    def fake_build(
        provider_id,
        provider_record,
        model,
        *,
        proxy=None,
        web_search_native=True,
        tool_max_retries=3,
    ):
        captured["provider_id"] = provider_id
        captured["provider_record"] = provider_record
        captured["model"] = model
        captured["proxy"] = proxy
        captured["web_search_native"] = web_search_native
        captured["tool_max_retries"] = tool_max_retries
        return FakeAgent(FakeResult("hi"))

    monkeypatch.setattr(chat.providers, "build_agent", fake_build)
    monkeypatch.setattr(chat.sv, "check_enabled", lambda scope: True)
    sent = _stub_send(monkeypatch)

    bot, event = _milky_group("#hi", user_id=7)
    await bot.handle_event(event)

    assert captured["provider_id"] == "anthropic"
    assert captured["provider_record"].id == "anthropic"
    assert captured["model"] == "claude-3-5-sonnet"
    assert captured["proxy"] == chat.get_config().proxy
    assert captured["web_search_native"] is True
    assert captured["tool_max_retries"] == 3
    assert len(sent) == 1


# ------------------------------------------------------- 观测日志


def test_format_run_trace_lines():
    """RunLog.nodes 格式化为可读轨迹行：step/tools（脱敏参数+思考）/end。"""
    from hoshino.ai.runner import RunLog

    from hoshino.modules.ai.chat import _format_run_trace

    run_log = RunLog(started_at=100.0)
    run_log.nodes = [
        {"type": "model_request", "ts": 101.0, "detail": "user: 你好"},
        {
            "type": "tools",
            "ts": 102.0,
            "detail": {
                "calls": [{"name": "web_search", "args_summary": "{q=<4>}"}],
                "introspection": "用户想查天气",
            },
        },
        {
            "type": "model_request",
            "ts": 103.5,
            "detail": "tool web_search → 找到 3 条结果",
        },
        {"type": "end", "ts": 104.0},
    ]
    lines = _format_run_trace(run_log)
    assert len(lines) == 4
    assert lines[0].startswith("step 1 model_request") and "user: 你好" in lines[0]
    assert "web_search" in lines[1] and "思考: 用户想查天气" in lines[1]
    assert lines[2].startswith("step 2 model_request")
    assert "找到 3 条结果" in lines[2]
    assert lines[3] == "end · 0.5s"


def test_format_run_trace_empty():
    from hoshino.ai.runner import RunLog

    from hoshino.modules.ai.chat import _format_run_trace

    assert _format_run_trace(RunLog()) == []


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_chat_success_logs_step_trace_and_reply(monkeypatch, tmp_store):
    """成功路径：运行日志逐行输出 step/tools 轨迹与回复摘要，便于观测。"""
    from loguru import logger as loguru_logger

    from hoshino.modules.ai import chat

    _stub_config(monkeypatch, tmp_store)

    class TracedRun(FakeAgentRun):
        """产出带名字的假图节点（ModelRequestNode/CallToolsNode/End）。"""

        def __init__(self, result):
            super().__init__(result)
            self._nodes = [
                type("ModelRequestNode", (), {})(),
                type(
                    "CallToolsNode",
                    (),
                    {
                        "model_response": type(
                            "ModelResponse",
                            (),
                            {
                                "parts": [
                                    type(
                                        "ThinkingPart", (), {"content": "我先查一下"}
                                    )(),
                                    type(
                                        "ToolCallPart",
                                        (),
                                        {
                                            "tool_name": "web_search",
                                            "args": {"q": "secret-keyword"},
                                        },
                                    )(),
                                ]
                            },
                        )()
                    },
                )(),
                type("End", (), {})(),
            ]
            self._index = 0

        async def __anext__(self):
            if self._index < len(self._nodes):
                node = self._nodes[self._index]
                self._index += 1
                return node
            self.result = self._result
            raise StopAsyncIteration

    class TracedAgent(FakeAgent):
        def iter(self, prompt, **kwargs):
            self.prompt = prompt
            return TracedRun(self._result)

    agent = TracedAgent(FakeResult("**查到了**"))
    monkeypatch.setattr(chat.providers, "build_agent", lambda *a, **k: agent)
    monkeypatch.setattr(chat.sv, "check_enabled", lambda scope: True)

    async def fake_render(md, cfg):
        return b"FAKEPNG"

    monkeypatch.setattr(chat.rendering, "render_markdown", fake_render)
    sent = _stub_send(monkeypatch)

    records: list[str] = []
    sink_id = loguru_logger.add(records.append, format="{message}", level="INFO")
    try:
        bot, event = _milky_group("#查一下", user_id=7)
        await bot.handle_event(event)
    finally:
        loguru_logger.remove(sink_id)

    joined = "\n".join(records)
    # 汇总行：steps / tokens / 耗时
    assert "AI 请求成功" in joined
    assert "steps=1" in joined  # 假图里只有一个 ModelRequestNode
    assert "耗时=" in joined
    # 轨迹行：模型请求（含上一动作）→ 工具调用（脱敏参数 + 思考）→ end
    assert "AI trace" in joined
    assert "step 1 model_request" in joined
    assert "web_search" in joined
    assert "{q=<14>}" in joined  # secret-keyword 脱敏为长度
    assert "思考: 我先查一下" in joined
    assert "end ·" in joined
    # 回复摘要行
    assert "AI 回复" in joined
    assert "摘要「**查到了**」" in joined
    assert len(sent) == 1


# ------------------------------------------------------- run_agent 契约


async def test_run_agent_emits_node_events_and_returns_result():
    """run_agent 是协程：逐节点回调 on_event，结束后返回最终结果。"""
    from hoshino.ai import runner

    agent = FakeAgent(FakeResult("done"))
    events: list = []
    result = await runner.run_agent(agent, "p", deps=object(), on_event=events.append)

    assert isinstance(result, FakeResult)
    assert len(events) == 1
    assert type(events[0]).__name__ == "RunEvent"
    assert events[0].result is None if hasattr(events[0], "result") else True


async def test_run_agent_propagates_agent_error():
    from hoshino.ai import runner

    agent = FakeAgent(FakeResult("x"), error=RuntimeError("boom"))
    with pytest.raises(RuntimeError, match="boom"):
        await runner.run_agent(agent, "p", deps=object())


# ------------------------------------------------------- cancel scope 回归


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_chat_run_exits_agent_iter_scope_in_task(monkeypatch, tmp_store):
    """回归：run 结束后 agent.iter 的 anyio scope 必须在原任务内退出。

    此前 chat 在 run_agent 异步生成器中拿到结果就提前 return，迭代器悬空在
    ``async with agent.iter(...)`` 内等 GC 关闭。pydantic_graph 在 agent.iter
    内 enter 的 anyio CancelScope 因此泄漏在 matcher 任务的 scope 栈上，随后
    NoneBot run_coro_with_shield 退出 shield CancelScope 时报
    "Attempted to exit a cancel scope that isn't the current tasks's current
    cancel scope"（每次 ``#`` 聊天成功回复后都记一条 ERROR）。
    """
    import asyncio

    import anyio
    from anyio._backends._asyncio import _task_states

    from hoshino.modules.ai import chat

    class ScopedAgentRun(FakeAgentRun):
        # 模拟 pydantic-ai/pydantic_graph 的 AgentRun：上下文期间在当前任务
        # 持有一个 anyio CancelScope（graph_builder 的 with CancelScope()）。
        async def __aenter__(self):
            self._scope = anyio.CancelScope()
            self._scope.__enter__()
            return await super().__aenter__()

        async def __aexit__(self, *exc):
            try:
                return await super().__aexit__(*exc)
            finally:
                self._scope.__exit__(None, None, None)

    class ScopedAgent(FakeAgent):
        def iter(self, prompt, **kwargs):
            self.prompt = prompt
            self.message_history = kwargs.get("message_history")
            return ScopedAgentRun(self._result, self._error)

    def current_scope():
        state = _task_states.get(asyncio.current_task())
        return None if state is None else state.cancel_scope

    _stub_config(monkeypatch, tmp_store)
    agent = ScopedAgent(FakeResult("hi"))
    monkeypatch.setattr(chat.providers, "build_agent", lambda *a, **k: agent)

    async def fake_render(md, cfg):
        return b"FAKEPNG"

    monkeypatch.setattr(chat.rendering, "render_markdown", fake_render)
    monkeypatch.setattr(chat.sv, "check_enabled", lambda scope: True)
    sent = _stub_send(monkeypatch)

    scope_before = current_scope()
    bot, event = _milky_group("#你好", user_id=7)
    await bot.handle_event(event)

    assert agent.prompt == "你好"
    assert len(sent) == 1
    # scope 栈必须回到 dispatch 前的状态，否则 NoneBot shield scope 退出会报错。
    assert current_scope() is scope_before


# ------------------------------------------------------- 多对话（上下文）管理


def _chat_env(monkeypatch, tmp_store, **config_overrides):
    """聊天行为测试公共 stub：config/provider/render/service/send。"""
    from hoshino.modules.ai import chat

    _stub_config(monkeypatch, tmp_store, **config_overrides)
    agent = FakeAgent(FakeResult("回答"))
    monkeypatch.setattr(chat.providers, "build_agent", lambda *a, **k: agent)

    async def fake_render(md, cfg):
        return b"FAKEPNG"

    monkeypatch.setattr(chat.rendering, "render_markdown", fake_render)
    monkeypatch.setattr(chat.sv, "check_enabled", lambda scope: True)
    sent = _stub_send(monkeypatch)
    return agent, sent


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_conv_new_creates_and_switches(monkeypatch, tmp_store):
    from hoshino.ai import sessions

    _, sent = _chat_env(monkeypatch, tmp_store)
    manager = sessions.conversation_manager

    bot, event = _milky_group("#new 旅游计划", user_id=7)
    await bot.handle_event(event)
    assert "已新建并切换到对话 `旅游计划`" in sent[-1][1].extract_plain_text()
    assert manager.get_active("milky:123456").name == "旅游计划"

    # 重名拒绝
    bot, event = _milky_group("#new 旅游计划", user_id=7)
    await bot.handle_event(event)
    assert "已存在" in sent[-1][1].extract_plain_text()


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_conv_new_with_extra_tokens_is_chat(monkeypatch, tmp_store):
    """`#new` 后超过一个 token 时按聊天处理（名字不含空白，整词精确匹配）。"""
    agent, sent = _chat_env(monkeypatch, tmp_store)

    bot, event = _milky_group("#new a b", user_id=7)
    await bot.handle_event(event)

    assert agent.prompt == "new a b"


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_conv_switch_and_list(monkeypatch, tmp_store):
    from hoshino.ai import sessions

    agent, sent = _chat_env(monkeypatch, tmp_store)
    manager = sessions.conversation_manager

    # 先聊一轮：全新 scope 自动建「默认」对话
    bot, event = _milky_group("#hello", user_id=7)
    await bot.handle_event(event)
    assert agent.prompt == "hello"

    bot, event = _milky_group("#new 甲", user_id=7)
    await bot.handle_event(event)
    bot, event = _milky_group("#switch 默认", user_id=7)
    await bot.handle_event(event)
    assert "已切换到对话 `默认`" in sent[-1][1].extract_plain_text()
    assert manager.get_active("milky:123456").name == "默认"

    # 不存在的对话：列出可用
    bot, event = _milky_group("#switch 幽灵", user_id=7)
    await bot.handle_event(event)
    text = sent[-1][1].extract_plain_text()
    assert "不存在" in text and "甲" in text

    # list 展示全部对话与激活标记
    bot, event = _milky_group("#list", user_id=7)
    await bot.handle_event(event)
    text = sent[-1][1].extract_plain_text()
    assert "* 默认" in text and "甲" in text


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_conv_isolation_across_switch(monkeypatch, tmp_store):
    """切换后聊天写入新对话，旧对话不受影响。"""
    from pydantic_ai.messages import ModelRequest, UserPromptPart

    from hoshino.ai import sessions

    agent, sent = _chat_env(monkeypatch, tmp_store)
    manager = sessions.conversation_manager

    # 「默认」里聊一轮（FakeResult.messages 落进历史）
    agent._result = FakeResult(
        "回答一", messages=[ModelRequest(parts=[UserPromptPart(content="问题一")])]
    )
    bot, event = _milky_group("#问题一", user_id=7)
    await bot.handle_event(event)
    assert len(manager.get_active("milky:123456").messages) == 1

    # 切到新对话再聊：新对话有自己的历史
    bot, event = _milky_group("#new 乙", user_id=7)
    await bot.handle_event(event)
    agent._result = FakeResult(
        "回答二", messages=[ModelRequest(parts=[UserPromptPart(content="问题二")])]
    )
    bot, event = _milky_group("#问题二", user_id=7)
    await bot.handle_event(event)

    assert manager.get_active("milky:123456").name == "乙"
    assert len(manager.get_active("milky:123456").messages) == 1
    # 旧对话历史仍在
    assert manager.find("milky:123456", "默认") is not None
    assert len(manager.find("milky:123456", "默认").messages) == 1


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_conv_persists_across_manager_rebuild(monkeypatch, tmp_store):
    """write-through 落库：重建 manager（模拟重启）后上下文仍在。"""
    from pydantic_ai.messages import ModelRequest, UserPromptPart

    from hoshino.ai import sessions

    agent, sent = _chat_env(monkeypatch, tmp_store)
    agent._result = FakeResult(
        "回答", messages=[ModelRequest(parts=[UserPromptPart(content="问题")])]
    )
    bot, event = _milky_group("#问题", user_id=7)
    await bot.handle_event(event)

    # 模拟进程重启：全新 manager，缓存为空，从 DB 惰性载入
    monkeypatch.setattr(
        sessions, "conversation_manager", sessions.ConversationManager()
    )
    conv = sessions.conversation_manager.get_active("milky:123456")
    assert conv.name == "默认"
    assert len(conv.messages) == 1


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_conv_clear_requires_admin_in_group(monkeypatch, tmp_store):
    _, sent = _chat_env(monkeypatch, tmp_store)

    bot, event = _milky_group("#clear", user_id=43, role="member")
    await bot.handle_event(event)
    assert "管理员权限" in sent[-1][1].extract_plain_text()

    bot, event = _milky_group("#clear", user_id=7, role="admin")
    await bot.handle_event(event)
    assert (
        "已清空" in sent[-1][1].extract_plain_text()
        or "没有可清空" in sent[-1][1].extract_plain_text()
    )


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_chat_busy_replies_when_turn_in_progress(monkeypatch, tmp_store):
    """run 进行中再收 # → 忙提示，且不产生第二次 run。"""
    from hoshino.ai import sessions

    agent, sent = _chat_env(monkeypatch, tmp_store)
    manager = sessions.conversation_manager

    lock = manager.turn_lock("milky:123456")
    await lock.acquire()
    try:
        bot, event = _milky_group("#你好", user_id=7)
        await bot.handle_event(event)
    finally:
        lock.release()

    assert "还在处理中" in sent[-1][1].extract_plain_text()
    assert getattr(agent, "prompt", None) is None  # FakeAgent 未被驱动


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_chat_run_timeout_keeps_prompt(monkeypatch, tmp_store):
    """墙钟超时：回复超时提示，本轮提问写入上下文可续问。"""
    import asyncio as _asyncio

    from hoshino.ai import sessions
    from hoshino.modules.ai import chat

    agent, sent = _chat_env(monkeypatch, tmp_store, chat_run_timeout_seconds=0.05)

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

    slow = SlowAgent(FakeResult("回答"))
    monkeypatch.setattr(chat.providers, "build_agent", lambda *a, **k: slow)
    manager = sessions.conversation_manager

    bot, event = _milky_group("#慢慢来", user_id=7)
    await bot.handle_event(event)

    assert "超时" in sent[-1][1].extract_plain_text()
    messages = manager.get_active("milky:123456").messages
    assert len(messages) == 1  # 提问已保留在上下文
    assert slow.prompt == "慢慢来"


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_chat_usage_limit_keeps_prompt(monkeypatch, tmp_store):
    """UsageLimit 超限与超时同语义：保留提问。"""
    from pydantic_ai.exceptions import UsageLimitExceeded

    from hoshino.ai import sessions

    agent, sent = _chat_env(monkeypatch, tmp_store)
    agent._error = UsageLimitExceeded("too many requests")
    manager = sessions.conversation_manager

    bot, event = _milky_group("#循环了", user_id=7)
    await bot.handle_event(event)

    assert "超出步数限制" in sent[-1][1].extract_plain_text()
    assert len(manager.get_active("milky:123456").messages) == 1


# ------------------------------------------------------- 拦截瀑布（pre-step / retry）


@pytest.mark.usefixtures("_nonebot_bootstrap", "_reset_hooks")
async def test_chat_pre_step_reject_blocks_run(monkeypatch, tmp_store):
    """pre-step reject：回固定文案、不跑模型、不写事件。"""
    from hoshino.ai import hooks
    from hoshino.ai import sessions
    from hoshino.modules.ai import chat

    _stub_config(monkeypatch, tmp_store)
    agent = FakeAgent(FakeResult("x"))
    monkeypatch.setattr(chat.providers, "build_agent", lambda *a, **k: agent)
    monkeypatch.setattr(chat.sv, "check_enabled", lambda scope: True)
    sent = _stub_send(monkeypatch)

    hooks.register_pre_step(lambda ctx: hooks.PreStepDecision.reject("这条不能回答"))

    bot, event = _milky_group("#你好", user_id=7)
    await bot.handle_event(event)

    assert getattr(agent, "prompt", None) is None  # 未驱动模型
    assert "这条不能回答" in sent[-1][1].extract_plain_text()
    # 不写事件
    assert sessions.conversation_manager.get_active("milky:123456").messages == []


@pytest.mark.usefixtures("_nonebot_bootstrap", "_reset_hooks")
async def test_chat_pre_step_rewrite_changes_model_prompt(monkeypatch, tmp_store):
    """pre-step rewrite：模型看到改写后的 prompt（surface 仍为用户原话）。"""
    from hoshino.ai import hooks

    agent, sent = _chat_env(monkeypatch, tmp_store)

    hooks.register_pre_step(
        lambda ctx: hooks.PreStepDecision.rewrite(ctx.prompt + "（系统注入）")
    )

    bot, event = _milky_group("#你好", user_id=7)
    await bot.handle_event(event)

    assert agent.prompt == "你好（系统注入）"
    assert len(sent) == 1


@pytest.mark.usefixtures("_nonebot_bootstrap", "_reset_hooks")
async def test_chat_retries_transient_first_request_error(monkeypatch, tmp_store):
    """瞬态 provider 异常（429）且尚无工具调用：同轮有界重试后成功。"""
    from pydantic_ai.exceptions import ModelHTTPError

    from hoshino.modules.ai import chat

    agent = RetryAgent(ModelHTTPError(429, "deepseek"))
    monkeypatch.setattr(chat.providers, "build_agent", lambda *a, **k: agent)
    sent = _stub_send(monkeypatch)

    async def fake_render(md, cfg):
        return b"FAKEPNG"

    _stub_config(monkeypatch, tmp_store)
    monkeypatch.setattr(chat.rendering, "render_markdown", fake_render)
    monkeypatch.setattr(chat.sv, "check_enabled", lambda scope: True)

    bot, event = _milky_group("#你好", user_id=7)
    await bot.handle_event(event)

    assert agent._calls == 2  # 重试了一次
    assert len(sent) == 1
    assert [segment.type for segment in sent[0][1]] == ["image"]


@pytest.mark.usefixtures("_nonebot_bootstrap", "_reset_hooks")
async def test_chat_does_not_retry_non_transient_error(monkeypatch, tmp_store):
    """非瞬态异常不重试，直接按失败回复。"""
    from hoshino.modules.ai import chat

    agent = RetryAgent(RuntimeError("boom"))
    monkeypatch.setattr(chat.providers, "build_agent", lambda *a, **k: agent)
    sent = _stub_send(monkeypatch)
    _stub_config(monkeypatch, tmp_store)
    monkeypatch.setattr(chat.sv, "check_enabled", lambda scope: True)

    bot, event = _milky_group("#你好", user_id=7)
    await bot.handle_event(event)

    assert agent._calls == 1
    assert "AI 请求失败" in sent[-1][1].extract_plain_text()


async def test_run_agent_with_retry_skips_when_tools_called():
    """副作用守卫：已有工具调用时不重试（避免重放副作用）。"""
    from pydantic_ai.exceptions import ModelHTTPError

    from hoshino.ai import runner

    agent = RetryAgent(ModelHTTPError(429, "deepseek"))
    run_log = runner.RunLog()
    run_log.tool_calls.append({"name": "bash", "args_summary": "{}"})

    with pytest.raises(ModelHTTPError):
        await runner.run_agent_with_retry(
            agent, "p", deps=_RetryDeps(), run_log=run_log, max_retries=2
        )
    assert agent._calls == 1  # 不重试


# ------------------------------------------------------- 目标（goal）命令


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_goal_set_view_and_transition(monkeypatch, tmp_store):
    _, sent = _chat_env(monkeypatch, tmp_store)

    bot, event = _milky_group("#goal set 学习 dsh agent", user_id=7)
    await bot.handle_event(event)
    assert "已设定目标" in sent[-1][1].extract_plain_text()

    bot, event = _milky_group("#goal", user_id=7)
    await bot.handle_event(event)
    text = sent[-1][1].extract_plain_text()
    assert "学习 dsh agent" in text
    assert "进行中" in text

    bot, event = _milky_group("#goal done", user_id=7)
    await bot.handle_event(event)
    assert "已完成" in sent[-1][1].extract_plain_text()


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_goal_set_requires_objective(monkeypatch, tmp_store):
    _, sent = _chat_env(monkeypatch, tmp_store)

    bot, event = _milky_group("#goal set", user_id=7)
    await bot.handle_event(event)
    assert "用法" in sent[-1][1].extract_plain_text()


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_goal_clear_requires_admin_in_group(monkeypatch, tmp_store):
    _, sent = _chat_env(monkeypatch, tmp_store)

    bot, event = _milky_group("#goal set 目标", user_id=7)
    await bot.handle_event(event)

    bot, event = _milky_group("#goal clear", user_id=43, role="member")
    await bot.handle_event(event)
    assert "管理员权限" in sent[-1][1].extract_plain_text()

    bot, event = _milky_group("#goal clear", user_id=7, role="admin")
    await bot.handle_event(event)
    assert "已清除" in sent[-1][1].extract_plain_text()
