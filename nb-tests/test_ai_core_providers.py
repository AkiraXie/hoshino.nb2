"""provider 层真实 HTTP 链路测试：本地 fake 服务器模拟 OpenAI / Anthropic API。

与 test_ai_chat.py 的 stub 策略互补——那里 stub 掉 ``build_agent`` 验证行为路径；这里用
``fake_ai_server``（本地 ``ThreadingHTTPServer``）让 ``build_model``/``build_agent`` 真正发出
HTTP 请求，验证请求格式（路径、鉴权 header、body）与响应解析。不连接真实模型、不依赖外网。

回归覆盖：``ApprovalRequiredToolset`` 必须包装 ``DynamicToolset``（缺 ``wrapped`` 会抛
``TypeError``，见 providers.build_agent 的 toolsets 组装）。
"""

from __future__ import annotations

import pytest
from nonebot_plugin_alconna.uniseg import Target

from hoshino.ai.config import AIConfig
from hoshino.ai.deps import AgentDeps, PermissionSnapshot, Telemetry
from hoshino.ai.provider import ProviderRecord


@pytest.fixture(autouse=True)
def _cleanup_agent_cache():
    """每个测试后关闭 build_model 创建的 http client，避免泄漏。"""
    yield
    from hoshino.ai.providers import clear_agent_cache

    clear_agent_cache()


def _make_deps(base_url: str, provider_id: str, model: str) -> AgentDeps:
    config = AIConfig(system_prompt="你是测试助手。", default="openai")
    return AgentDeps(
        surface="chat",
        scope_key=None,
        target=Target(id="0", private=True, self_id="10000", adapter="milky"),
        config=config,
        permissions=PermissionSnapshot(),
        bot=None,
        event=None,
        telemetry=Telemetry(provider_id=provider_id, scope_key="", model=model),
    )


# ------------------------------------------------------------ toolsets 回归


# ------------------------------------------------------------ HTTP roundtrip


def test_openai_chat_roundtrip(fake_ai_server, tmp_store):
    """openai_chat 走真实 HTTP：请求路径 /chat/completions、Bearer 鉴权、body 正确。"""
    base_url, requests = fake_ai_server
    from hoshino.ai.providers import build_agent

    record = ProviderRecord(
        id="openai",
        url=base_url,
        key="sk-test-openai",
        kind="openai_chat",
    )
    agent = build_agent("openai", record, "gpt-4o-mini")
    result = agent.run_sync("你好", deps=_make_deps(base_url, "openai", "gpt-4o-mini"))

    assert result.output == "你好，我是 OpenAI 回复"
    assert result.usage.total_tokens == 15  # prompt 10 + completion 5

    assert len(requests) == 1
    req = requests[0]
    assert req["stem"].endswith("/chat/completions")
    assert req["headers"]["authorization"] == "Bearer sk-test-openai"
    assert req["body"]["model"] == "gpt-4o-mini"
    assert req["body"]["messages"][-1]["content"] == "你好"


def test_anthropic_roundtrip(fake_ai_server, tmp_store):
    """anthropic 走真实 HTTP：路径 /v1/messages（含 ?beta=true）、x-api-key、body 正确。"""
    base_url, requests = fake_ai_server
    from hoshino.ai.providers import build_agent

    record = ProviderRecord(
        id="anthropic",
        url=base_url,
        key="sk-ant-test-123",
        kind="anthropic",
    )
    agent = build_agent("anthropic", record, "claude-3-5-sonnet")
    result = agent.run_sync("你好", deps=_make_deps(base_url, "anthropic", "claude-3-5-sonnet"))

    assert result.output == "你好，我是 Claude 回复"
    assert result.usage.total_tokens == 15  # input 10 + output 5

    assert len(requests) == 1
    req = requests[0]
    assert req["stem"].endswith("/v1/messages")
    assert "beta=true" in req["path"]  # anthropic SDK 自带 beta query
    assert req["headers"]["x-api-key"] == "sk-ant-test-123"
    assert req["body"]["model"] == "claude-3-5-sonnet"
    last = req["body"]["messages"][-1]
    assert last["role"] == "user"
    assert last["content"][0]["text"] == "你好"


# ------------------------------------------------------------ 联网搜索（web_search 工具）


def _tools_in(requests: list[dict]) -> list[dict]:
    """提取最后一次请求 body 里的 tools 列表（Anthropic 格式）。"""
    return (requests[-1]["body"].get("tools") or []) if requests else []


def _native_search_tool(tools: list[dict]) -> dict | None:
    return next((t for t in tools if t.get("type") == "web_search_20250305"), None)


def _search_deps(base_url: str, provider_id: str, *, model: str = "deepseek-v4-flash") -> AgentDeps:
    """web_search 工具的 deps：config.default 指向待测 provider。"""
    config = AIConfig(system_prompt="你是测试助手。", default=provider_id)
    return AgentDeps(
        surface="chat",
        scope_key=None,
        target=Target(id="0", private=True, self_id="10000", adapter="milky"),
        config=config,
        permissions=PermissionSnapshot(),
        bot=None,
        event=None,
        telemetry=Telemetry(provider_id=provider_id, scope_key="", model=model),
    )


def _seed_search_config(
    tmp_store, kind: str, *, url: str = "", key: str = "", model: str = ""
) -> None:
    """写入搜索 provider 配置（``ai search set`` 的 DB 语义）。"""
    tmp_store.set_search_provider(kind, url=url, key=key, model=model)


def _seed_chat_provider(
    tmp_store, base_url: str, *, provider_id: str = "anthropic", kind: str = "anthropic"
) -> None:
    """预置聊天 provider 行（deepseek 默认搜索只借 key）。"""
    tmp_store.upsert_provider_row(
        provider_id=provider_id,
        url=base_url,
        key="sk-ant-test-123",
        kind=kind,
    )
    tmp_store.set_global_value("default_model_provider", provider_id)
    tmp_store.set_global_value("default_model", "deepseek-v4-flash")


def test_web_search_deepseek_request_and_results(fake_ai_server, tmp_store):
    """deepseek 搜索：Anthropic Messages 端点 + 服务端 web_search_20250305。

    响应里的 ``web_search_tool_result`` 块 + ``citations`` 拼成可读结果。
    base 不带 /v1 时先试 ``{base}/messages``（404）再回退 ``{base}/v1/messages``。
    """
    import asyncio
    from types import SimpleNamespace

    from fake_ai_server import SEARCH_RESPONSE, _FakeHandler
    from hoshino.ai.tools.web.web_search import web_search

    _FakeHandler.search_response = SEARCH_RESPONSE
    base_url, requests = fake_ai_server
    _seed_search_config(tmp_store, "deepseek", url=base_url, key="sk-ant-test-123")

    out = asyncio.run(
        web_search(SimpleNamespace(deps=_search_deps(base_url, "anthropic")), "今天的天气")
    )

    assert "示例结果 A" in out
    assert "https://example.com/result-a" in out
    assert "这是结果 A 的摘要。" in out
    assert "示例结果 B" in out
    assert "（2 条）" in out
    # 请求格式：先 404 探测 {base}/messages，再命中 /v1/messages；
    # x-api-key 鉴权、服务端 web_search 工具、搜索 prompt。
    assert [r["stem"] for r in requests] == ["/messages", "/v1/messages"]
    req = requests[1]
    assert req["headers"]["x-api-key"] == "sk-ant-test-123"
    assert req["headers"]["authorization"] == "Bearer sk-ant-test-123"
    assert req["body"]["model"] == "deepseek-v4-flash"  # 未配模型 → 默认
    assert _native_search_tool(req["body"].get("tools") or []) is not None
    prompt = req["body"]["messages"][-1]["content"][0]["text"]
    assert prompt == "Perform a web search for the query: 今天的天气"


def test_web_search_default_borrows_chat_provider_key(fake_ai_server, tmp_store, monkeypatch):
    """默认 deepseek：未配置搜索时只借聊天 provider key，url/model 用 DEFAULT_*。"""
    import asyncio
    from types import SimpleNamespace

    from fake_ai_server import SEARCH_RESPONSE, _FakeHandler
    from hoshino.ai import search as search_domain
    from hoshino.ai.tools.web.web_search import web_search

    _FakeHandler.search_response = SEARCH_RESPONSE
    base_url, requests = fake_ai_server
    monkeypatch.setattr(search_domain, "DEFAULT_DEEPSEEK_URL", base_url)
    _seed_chat_provider(tmp_store, "https://chat.example.com")  # 聊天 url 不参与搜索

    out = asyncio.run(web_search(SimpleNamespace(deps=_search_deps(base_url, "anthropic")), "q"))
    assert "示例结果 A" in out
    req = requests[1]  # /messages 404 探测 + /v1/messages 命中
    assert req["headers"]["x-api-key"] == "sk-ant-test-123"
    assert req["body"]["model"] == "deepseek-v4-flash"


def test_web_search_no_config_without_chat_key_reports(tmp_store):
    """无搜索配置且无可借聊天 key：提示未配置，不发请求。"""
    import asyncio
    from types import SimpleNamespace

    from hoshino.ai.tools.web.web_search import web_search

    out = asyncio.run(
        web_search(
            SimpleNamespace(deps=_search_deps("http://127.0.0.1:1", "openai", model="gpt-4o-mini")),
            "q",
        )
    )
    assert "未配置搜索 provider" in out
    assert "ai search set" in out


def test_web_search_tavily(fake_ai_server, tmp_store, monkeypatch):
    """tavily 搜索：端点写死 api.tavily.com，POST /search，Bearer 鉴权。"""
    import asyncio
    from types import SimpleNamespace

    from hoshino.ai import search as search_domain
    from hoshino.ai.tools.web.web_search import web_search

    base_url, requests = fake_ai_server
    # 端点写死：测试里把内置常量指到 fake 服务器。
    monkeypatch.setattr(search_domain, "DEFAULT_TAVILY_URL", base_url)
    _seed_search_config(tmp_store, "tavily", key="tvly-test-key")  # url 配置被忽略

    out = asyncio.run(web_search(SimpleNamespace(deps=_search_deps(base_url, "openai")), "q"))
    assert "Tavily 结果" in out
    assert "https://example.com/tavily" in out
    assert "这是 Tavily 的摘要。" in out
    req = requests[0]
    assert req["stem"] == "/search"
    assert req["headers"]["authorization"] == "Bearer tvly-test-key"
    assert req["body"]["query"] == "q"
    assert req["body"]["max_results"] == 5


def test_web_search_bocha(fake_ai_server, tmp_store, monkeypatch):
    """博查搜索：端点写死 api.bocha.cn，POST /v1/web-search，Bearer 鉴权。"""
    import asyncio
    from types import SimpleNamespace

    from hoshino.ai import search as search_domain
    from hoshino.ai.tools.web.web_search import web_search

    base_url, requests = fake_ai_server
    # 端点写死：测试里把内置常量指到 fake 服务器。
    monkeypatch.setattr(search_domain, "DEFAULT_BOCHA_URL", base_url)
    _seed_search_config(tmp_store, "bocha", key="sk-bocha-key")  # url 配置被忽略

    out = asyncio.run(web_search(SimpleNamespace(deps=_search_deps(base_url, "openai")), "q"))
    assert "博查结果" in out
    assert "https://example.com/bocha" in out
    assert "这是博查的摘要。" in out
    req = requests[0]
    assert req["stem"] == "/v1/web-search"
    assert req["headers"]["authorization"] == "Bearer sk-bocha-key"
    assert req["body"]["query"] == "q"
    assert req["body"]["count"] == 5


def test_openai_system_prompt_and_placeholder_in_body(fake_ai_server, tmp_store):
    """系统提示随请求发出；token 占位符出现，说明动态 persona 解析生效。"""
    base_url, requests = fake_ai_server
    from hoshino.ai.providers import build_agent

    record = ProviderRecord(
        id="openai",
        url=base_url,
        key="sk-test-openai",
        kind="openai_chat",
    )
    agent = build_agent("openai", record, "gpt-4o-mini")
    agent.run_sync("hi", deps=_make_deps(base_url, "openai", "gpt-4o-mini"))

    req = requests[0]
    roles = [m["role"] for m in req["body"]["messages"]]
    assert "system" in roles
    system = next(m for m in req["body"]["messages"] if m["role"] == "system")
    assert "你是测试助手" in system["content"]
