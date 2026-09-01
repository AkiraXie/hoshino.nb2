"""AI chat 插件与公共基建测试：纯函数、SQLite、行为路径。

行为测试 stub ``providers`` / ``rendering``，不连接真实模型或浏览器。
"""

from __future__ import annotations

import pytest
from nonebot.adapters.milky import Bot as MilkyBot
from nonebot.adapters.milky.event import GroupMessageEvent as MilkyGroupMessageEvent
from nonebot.adapters.milky.model.api import MessageResponse
from pydantic_ai.usage import RunUsage

from _helpers import next_seq
from hoshino.ai.config import AIConfig

# _clear_uninfo_cache 和 _fresh_conversation_manager 由 modules/ai/conftest.py 提供。


def _milky_group(
    text: str,
    *,
    user_id: int = 42,
    role: str = "admin",
    group_id: int = 123456,
    reply: dict | None = None,
    segments: list[dict] | None = None,
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
                "segments": (
                    segments if segments is not None else [{"type": "text", "data": {"text": text}}]
                ),
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

    def with_prefix(self, prefix: list) -> FakeResult:
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
            return FakeAgentRun(FakeResult("x"), self._first_error, kwargs.get("message_history"))
        return FakeAgentRun(self._result, None, kwargs.get("message_history"))


class _RetryDeps:
    """run_agent_with_retry 构建 RequestErrorContext 所需的最小 deps 替身。"""

    scope_key = "milky:1"
    surface = "chat"

    class Telemetry:
        provider_id = "openai"

    # runner.RequestErrorContext 以属性名 ``deps.telemetry`` 访问，保留小写别名。
    telemetry = Telemetry


@pytest.fixture
def _reset_hooks():
    """钩子注册表是模块全局，每个测试前后清空。"""
    from hoshino.ai import hooks

    hooks.reset_hooks()
    yield
    hooks.reset_hooks()


def _stub_config(monkeypatch, tmp_store, *, seed_providers: bool = True, **overrides):
    from hoshino.modules.ai import chat

    defaults = {
        "default": "openai",
        "system_prompt": "你是测试助手。",
        "max_history_messages": 40,
        "render_timeout_seconds": 30.0,
        "render_theme": "light",
    }
    defaults.update(overrides)
    config = AIConfig(**defaults)
    monkeypatch.setattr(chat, "get_config", lambda: config)
    if seed_providers:
        # provider 存 DB（唯一事实源）：预置两个 provider；全局默认 model 走 KV。
        tmp_store.upsert_provider_row(
            provider_id="openai",
            url="https://api.example.com/v1",
            key="sk-abcdefghij",
            kind="openai_chat",
        )
        tmp_store.upsert_provider_row(
            provider_id="anthropic",
            url="https://api.anthropic.com",
            key="sk-ant-1234567890",
            kind="anthropic",
        )
        tmp_store.set_global_value("default_model_provider", "openai")
        tmp_store.set_global_value("default_model", "gpt-4o-mini")
    return config


def _stub_send(monkeypatch):
    sent: list[tuple[int, object]] = []

    async def fake_send_group_message(self, *, group_id: int, message):
        sent.append((group_id, message))
        return MessageResponse(message_seq=8, time=1)

    monkeypatch.setattr(MilkyBot, "send_group_message", fake_send_group_message)
    return sent


# ---------------------------------------------------------- 配置纯函数


# ------------------------------------------------------- provider 解析


def _seed_test_providers(tmp_store) -> AIConfig:
    """预置 openai/anthropic 两个 provider 行，返回默认指向 openai 的配置。"""
    tmp_store.upsert_provider_row(
        provider_id="openai",
        url="u",
        key="k",
        kind="openai_chat",
    )
    tmp_store.upsert_provider_row(
        provider_id="anthropic",
        url="u2",
        key="k2",
        kind="anthropic",
    )
    tmp_store.set_global_value("default_model_provider", "openai")
    tmp_store.set_global_value("default_model", "gpt-4o-mini")
    return AIConfig(default="openai")


# ------------------------------------------------------- 指标聚合


# ------------------------------------------------------- 渲染纯函数


# ------------------------------------------------------- SQLite store


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
async def test_chat_at_other_bot_with_hash_does_not_trigger(monkeypatch, tmp_store):
    """`@bot2 #xxx` 不应触发本 bot：纯文本提取会把 at 段丢掉误判为 `#xxx`。"""
    from hoshino.modules.ai import chat

    _stub_config(monkeypatch, tmp_store)
    agent = FakeAgent(FakeResult("x"))
    monkeypatch.setattr(chat.providers, "build_agent", lambda *a, **k: agent)
    monkeypatch.setattr(chat.sv, "check_enabled", lambda scope: True)
    sent = _stub_send(monkeypatch)

    # @ 另一个机器人（9999 ≠ self_id 10000）+ # 开头文本
    bot, event = _milky_group(
        "x",
        user_id=7,
        segments=[
            {"type": "mention", "data": {"user_id": 9999}},
            {"type": "text", "data": {"text": "#你好"}},
        ],
    )
    await bot.handle_event(event)

    assert sent == []  # 不触发，不响应


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_chat_at_self_with_hash_triggers(monkeypatch, tmp_store):
    """`@bot1 #xxx`（@ 自己）触发，# 前缀被剥离后进入对话。"""
    from hoshino.modules.ai import chat

    _stub_config(monkeypatch, tmp_store)
    agent = FakeAgent(FakeResult("你好！"))
    monkeypatch.setattr(chat.providers, "build_agent", lambda *a, **k: agent)
    monkeypatch.setattr(chat.sv, "check_enabled", lambda scope: True)
    sent = _stub_send(monkeypatch)

    bot, event = _milky_group(
        "x",
        user_id=7,
        segments=[
            {"type": "mention", "data": {"user_id": 10000}},
            {"type": "text", "data": {"text": "#你好"}},
        ],
    )
    await bot.handle_event(event)

    assert agent.prompt == "你好"
    assert len(sent) == 1


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
    assert "未配置模型" in message.extract_plain_text()
    assert "ai model default" in message.extract_plain_text()


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
async def test_chat_uses_default_provider(monkeypatch, tmp_store):
    from hoshino.modules.ai import chat

    _stub_config(monkeypatch, tmp_store)
    # 无 scope 绑定 → build_agent 收到全局默认 provider（openai）及其默认模型
    captured: dict = {}

    def fake_build(
        provider_id,
        provider_record,
        model,
        *,
        proxy=None,
        tool_max_retries=3,
    ):
        captured["provider_id"] = provider_id
        captured["provider_record"] = provider_record
        captured["model"] = model
        captured["proxy"] = proxy
        captured["tool_max_retries"] = tool_max_retries
        return FakeAgent(FakeResult("hi"))

    monkeypatch.setattr(chat.providers, "build_agent", fake_build)
    monkeypatch.setattr(chat.sv, "check_enabled", lambda scope: True)
    sent = _stub_send(monkeypatch)

    bot, event = _milky_group("#hi", user_id=7)
    await bot.handle_event(event)

    assert captured["provider_id"] == "openai"
    assert captured["provider_record"].id == "openai"
    assert captured["model"] == "gpt-4o-mini"
    assert captured["proxy"] == chat.get_config().proxy
    assert captured["tool_max_retries"] == 3
    assert len(sent) == 1


# ------------------------------------------------------- 观测日志


# ------------------------------------------------------- run_agent 契约


# ------------------------------------------------------- cancel scope 回归


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
    monkeypatch.setattr(sessions, "conversation_manager", sessions.ConversationManager())
    conv = sessions.conversation_manager.get_active("milky:123456")
    assert conv.name == "默认"
    assert len(conv.messages) == 1


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_chat_consecutive_turns_keep_history(monkeypatch, tmp_store):
    """连续 4 轮 # 对话（1-1a-2-2a-3-3a-4-4a）：每轮模型必须收到此前全部历史。

    第 2 轮发问时历史含 1+1a；第 3 轮含 1..2a；第 4 轮含 1..3a；顺序与内容
    逐条断言，确认事件日志派生历史不丢轮、不串轮。
    """
    from pydantic_ai.messages import (
        ModelRequest,
        ModelResponse,
        TextPart,
        UserPromptPart,
    )

    def _turn(question: str, answer: str) -> FakeResult:
        # 对齐真实 pydantic-ai：一轮 = user ModelRequest + assistant ModelResponse。
        return FakeResult(
            answer,
            messages=[
                ModelRequest(parts=[UserPromptPart(content=question)]),
                ModelResponse(parts=[TextPart(content=answer)]),
            ],
        )

    turns = [
        ("问题一", "回答一"),
        ("问题二", "回答二"),
        ("问题三", "回答三"),
        ("问题四", "回答四"),
    ]
    agent, sent = _chat_env(monkeypatch, tmp_store)
    for index, (question, answer) in enumerate(turns, start=1):
        agent._result = _turn(question, answer)
        bot, event = _milky_group(f"#{question}", user_id=7)
        await bot.handle_event(event)
        # 本轮模型收到的历史 = 此前所有轮（1..(i-1) 的 user+assistant）
        expected = 2 * (index - 1)
        assert len(agent.message_history) == expected, (
            f"第 {index} 轮应收到 {expected} 条历史，实际 {len(agent.message_history)}"
        )
        for prior in range(index - 1):
            q, a = turns[prior]
            assert agent.message_history[2 * prior].parts[0].content == q
            assert agent.message_history[2 * prior + 1].parts[0].content == a


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
async def test_chat_run_timeout_drops_prompt(monkeypatch, tmp_store):
    """墙钟超时：回复超时提示，本轮提问不写入上下文（避免污染历史）。"""
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

    assert "处理超时" in sent[-1][1].extract_plain_text()
    assert "本次对话未记录" in sent[-1][1].extract_plain_text()
    messages = manager.get_active("milky:123456").messages
    assert len(messages) == 0  # 提问不写入上下文
    assert slow.prompt == "慢慢来"


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_chat_usage_limit_drops_prompt(monkeypatch, tmp_store):
    """UsageLimit 超限与超时同语义：提问不写入上下文。"""
    from pydantic_ai.exceptions import UsageLimitExceeded

    from hoshino.ai import sessions

    agent, sent = _chat_env(monkeypatch, tmp_store)
    agent._error = UsageLimitExceeded("too many requests")
    manager = sessions.conversation_manager

    bot, event = _milky_group("#循环了", user_id=7)
    await bot.handle_event(event)

    assert "处理超出步数限制" in sent[-1][1].extract_plain_text()
    assert "本次对话未记录" in sent[-1][1].extract_plain_text()
    assert len(manager.get_active("milky:123456").messages) == 0


# ------------------------------------------------------- 拦截瀑布（pre-step / retry）


# ------------------------------------------------------- 目标（goal）命令


# ------------------------------------------------------------ 用量统计与实时日志


# -------------------------------------------------- 引用回复：触发与内容识别


def _milky_reply(sender_id: int, text: str, seq: int = 77) -> dict:
    """构造 Milky 引用消息对象（IncomingMessage 字典）。"""
    return {
        "message_scene": "group",
        "peer_id": 123456,
        "message_seq": seq,
        "sender_id": sender_id,
        "time": 1,
        "segments": [{"type": "text", "data": {"text": text}}],
    }


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_chat_reply_to_bot_without_hash_does_not_trigger(monkeypatch, tmp_store):
    """回复 bot 自己的消息但无 ``#`` 前缀不触发（回复本身不额外放行）。"""
    agent, sent = _chat_env(monkeypatch, tmp_store)

    bot, event = _milky_group("继续说说", user_id=7, reply=_milky_reply(10000, "之前的 AI 消息"))
    await bot.handle_event(event)

    assert getattr(agent, "prompt", None) is None
    assert sent == []


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_chat_reply_to_other_user_not_triggered(monkeypatch, tmp_store):
    """回复他人消息（非 bot）不触发 AI 对话。"""
    agent, sent = _chat_env(monkeypatch, tmp_store)

    bot, event = _milky_group("你好啊", user_id=7, reply=_milky_reply(42, "别人的话"))
    await bot.handle_event(event)

    assert getattr(agent, "prompt", None) is None
    assert sent == []


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_chat_reply_context_injected_into_prompt(monkeypatch, tmp_store):
    """``#`` 提问时，回复指向的内容（文字/转发）注入模型 prompt。"""
    agent, sent = _chat_env(monkeypatch, tmp_store)

    bot, event = _milky_group(
        "#看看这个", user_id=7, reply=_milky_reply(10000, "之前发的一段聊天记录")
    )
    await bot.handle_event(event)

    assert agent.prompt is not None
    assert "用户引用了上一条消息" in agent.prompt
    assert "之前发的一段聊天记录" in agent.prompt
    assert "看看这个" in agent.prompt


def _ob11_group_event(text: str, reply: dict | None = None):
    from nonebot.adapters.onebot.v11 import GroupMessageEvent, Message

    data = {
        "time": 1,
        "self_id": 10000,
        "post_type": "message",
        "message_type": "group",
        "sub_type": "normal",
        "user_id": 42,
        "message_id": 7,
        "group_id": 123456,
        "raw_message": text,
        "font": 0,
        "message": Message(text),
        "original_message": Message(text),
        "sender": {"user_id": 42, "nickname": "Alice", "role": "admin"},
        "to_me": False,
    }
    if reply is not None:
        data["reply"] = reply
    return GroupMessageEvent(**data)


def _ob11_reply(sender_id: int, message: list | None = None) -> dict:
    return {
        "time": 1,
        "message_type": "group",
        "message_id": 9001,
        "real_id": 9001,
        "sender": {
            "user_id": sender_id,
            "nickname": "x",
            "sex": "unknown",
            "age": 0,
        },
        "message": message or [],
    }


class _GetMsgDelegatingBot:
    """真实 OB11Bot 的委托包装：只覆盖 get_msg，adapter/self_id 走原 bot。"""

    def __init__(self, bot, response):
        self._bot = bot
        self._response = response

    @property
    def adapter(self):
        return self._bot.adapter

    @property
    def self_id(self):
        return self._bot.self_id

    async def get_msg(self, message_id):
        return self._response


def _ob11_reply_bot(response):
    from adapter_events import ob11_group_message

    bot, event = ob11_group_message("hi", to_me=False, reply=_ob11_reply(10000))
    return _GetMsgDelegatingBot(bot, response), event


def test_ob11_reply_content_fetched_via_get_msg():
    """OB11 reply 段只带 id：get_reply_content 经 get_msg 拉取原文。"""
    from hoshino.platform import get_reply_content

    bot, event = _ob11_reply_bot(
        {
            "time": 1,
            "message_type": "group",
            "message_id": 9001,
            "real_id": 9001,
            "sender": {"user_id": 10000},
            "message": [{"type": "text", "data": {"text": "被引用的原文"}}],
        }
    )
    content = asyncio_run(get_reply_content(bot, event))
    assert content is not None
    assert "被引用的原文" in str(content)


def test_ob11_reply_image_extracted_via_get_msg():
    """OB11 回复里的图片：经 get_msg 拉取后由 media 收集（修复回复图片识别）。"""
    from nonebot_plugin_alconna.uniseg import Image as UniImage

    from hoshino.util.media import get_event_media_segments

    bot, event = _ob11_reply_bot(
        {
            "time": 1,
            "message_type": "group",
            "message_id": 9001,
            "real_id": 9001,
            "sender": {"user_id": 10000},
            "message": [
                {
                    "type": "image",
                    "data": {"file": "abc.png", "url": "https://x/abc.png"},
                }
            ],
        }
    )
    segments = asyncio_run(get_event_media_segments(bot, event, UniImage))
    assert len(segments) == 1
    assert segments[0].url == "https://x/abc.png"


def asyncio_run(coro):
    import asyncio

    return asyncio.run(coro)
