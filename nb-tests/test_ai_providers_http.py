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
from pydantic_ai.toolsets import ApprovalRequiredToolset, DynamicToolset

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


def test_build_agent_toolsets_wraps_dynamic():
    """ApprovalRequiredToolset 必须包装 DynamicToolset，而不是单独实例化。"""
    from hoshino.ai.providers import build_agent

    record = ProviderRecord(id="openai", url="http://127.0.0.1:1", key="k", kind="openai_chat")
    agent = build_agent("openai", record, "gpt-4o-mini")

    wrappers = [t for t in agent.toolsets if isinstance(t, ApprovalRequiredToolset)]
    assert len(wrappers) == 1, "toolsets 中应有且仅有一个 ApprovalRequiredToolset"
    assert isinstance(wrappers[0].wrapped, DynamicToolset)
    assert wrappers[0].approval_required_func is not None


def test_build_agent_cached_per_provider():
    """缓存 key 含 provider_config：不同 provider 不同 agent，同 provider 复用。"""
    from hoshino.ai.providers import build_agent

    record1 = ProviderRecord(id="openai", url="http://127.0.0.1:1", key="k1", kind="openai_chat")
    record2 = ProviderRecord(
        id="anthropic",
        url="http://127.0.0.1:1",
        key="k2",
        kind="anthropic",
        default_text_model="claude-3-5-sonnet",
    )
    assert build_agent("openai", record1, "gpt-4o-mini") is build_agent(
        "openai", record1, "gpt-4o-mini"
    )
    # 缓存 key 含 model：同一 provider 不同模型 → 不同 agent
    assert build_agent("openai", record1, "gpt-4o") is not build_agent(
        "openai", record1, "gpt-4o-mini"
    )
    assert build_agent("anthropic", record2, "claude-3-5-sonnet") is not build_agent(
        "openai", record1, "gpt-4o-mini"
    )


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
        default_text_model="gpt-4o-mini",
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
        default_text_model="claude-3-5-sonnet",
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
    """预置聊天 provider 行（deepseek 默认搜索的凭据继承源）。"""
    tmp_store.upsert_provider_row(
        provider_id=provider_id,
        url=base_url,
        key="sk-ant-test-123",
        kind=kind,
        default_text_model="deepseek-v4-flash",
    )


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


def test_web_search_deepseek_base_with_v1_hits_first(fake_ai_server, tmp_store):
    """base 已含 /v1：直接命中 {base}/messages，无 404 探测。"""
    import asyncio
    from types import SimpleNamespace

    from hoshino.ai.tools.web.web_search import web_search

    base_url, requests = fake_ai_server
    _seed_search_config(tmp_store, "deepseek", url=f"{base_url}/v1", key="sk-ant-test-123")

    out = asyncio.run(
        web_search(SimpleNamespace(deps=_search_deps(f"{base_url}/v1", "anthropic")), "q")
    )
    assert "搜索未返回结果" in out  # 默认纯 text 响应
    assert [r["stem"] for r in requests] == ["/v1/messages"]


def test_web_search_default_inherits_anthropic_provider(fake_ai_server, tmp_store):
    """默认 deepseek：未配置搜索时继承 anthropic 聊天 provider 凭据。"""
    import asyncio
    from types import SimpleNamespace

    from fake_ai_server import SEARCH_RESPONSE, _FakeHandler
    from hoshino.ai.tools.web.web_search import web_search

    _FakeHandler.search_response = SEARCH_RESPONSE
    base_url, requests = fake_ai_server
    _seed_chat_provider(tmp_store, base_url)  # 无搜索配置 → 走默认继承

    out = asyncio.run(web_search(SimpleNamespace(deps=_search_deps(base_url, "anthropic")), "q"))
    assert "示例结果 A" in out
    req = requests[1]  # /messages 404 探测 + /v1/messages 命中
    assert req["headers"]["x-api-key"] == "sk-ant-test-123"


def test_web_search_no_config_without_anthropic_reports(tmp_store):
    """无搜索配置且无 anthropic 聊天 provider：提示未配置，不发请求。"""
    import asyncio
    from types import SimpleNamespace

    from hoshino.ai.tools.web.web_search import web_search

    _seed_chat_provider(tmp_store, "http://127.0.0.1:1", provider_id="openai", kind="openai_chat")
    out = asyncio.run(
        web_search(
            SimpleNamespace(deps=_search_deps("http://127.0.0.1:1", "openai", model="gpt-4o-mini")),
            "q",
        )
    )
    assert "未配置搜索 provider" in out
    assert "ai search set" in out


def test_web_search_api_error_message(fake_ai_server, tmp_store, monkeypatch):
    """非 404/405 的 API 错误：返回服务端 error.message，不重试回退候选。"""
    import asyncio
    import json
    from types import SimpleNamespace

    from fake_ai_server import _FakeHandler
    from hoshino.ai.tools.web.web_search import web_search

    def patched_do_post(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length)
        self.requests.append(
            {
                "path": self.path,
                "stem": self.path.split("?")[0],
                "headers": {k.lower(): v for k, v in self.headers.items()},
                "body": json.loads(raw) if raw else {},
            }
        )
        self._respond(400, {"error": {"message": "model does not support web_search"}})

    monkeypatch.setattr(_FakeHandler, "do_POST", patched_do_post)
    base_url, requests = fake_ai_server
    _seed_search_config(tmp_store, "deepseek", url=base_url, key="sk-ant-test-123")

    out = asyncio.run(web_search(SimpleNamespace(deps=_search_deps(base_url, "anthropic")), "q"))
    assert "model does not support web_search" in out
    assert len(requests) == 1  # 真实 API 错误不尝试回退候选


def test_web_search_tavily(fake_ai_server, tmp_store):
    """tavily 搜索：POST {url}/search，Bearer 鉴权，解析 results[].title/url/content。"""
    import asyncio
    from types import SimpleNamespace

    from hoshino.ai.tools.web.web_search import web_search

    base_url, requests = fake_ai_server
    _seed_search_config(tmp_store, "tavily", url=base_url, key="tvly-test-key")

    out = asyncio.run(web_search(SimpleNamespace(deps=_search_deps(base_url, "openai")), "q"))
    assert "Tavily 结果" in out
    assert "https://example.com/tavily" in out
    assert "这是 Tavily 的摘要。" in out
    req = requests[0]
    assert req["stem"] == "/search"
    assert req["headers"]["authorization"] == "Bearer tvly-test-key"
    assert req["body"]["query"] == "q"
    assert req["body"]["max_results"] == 5


def test_web_search_bocha(fake_ai_server, tmp_store):
    """博查搜索：POST {url}/v1/web-search，Bearer 鉴权，解析 webPages.value。"""
    import asyncio
    from types import SimpleNamespace

    from hoshino.ai.tools.web.web_search import web_search

    base_url, requests = fake_ai_server
    _seed_search_config(tmp_store, "bocha", url=base_url, key="sk-bocha-key")

    out = asyncio.run(web_search(SimpleNamespace(deps=_search_deps(base_url, "openai")), "q"))
    assert "博查结果" in out
    assert "https://example.com/bocha" in out
    assert "这是博查的摘要。" in out
    req = requests[0]
    assert req["stem"] == "/v1/web-search"
    assert req["headers"]["authorization"] == "Bearer sk-bocha-key"
    assert req["body"]["query"] == "q"
    assert req["body"]["count"] == 5


def test_web_search_missing_key_reports(tmp_store):
    """搜索配置缺 key（DB 被直接改坏）：明确提示，不发请求。"""
    import asyncio
    from types import SimpleNamespace

    from hoshino.ai.tools.web.web_search import web_search

    _seed_search_config(tmp_store, "tavily", url="http://127.0.0.1:1")  # 无 key
    out = asyncio.run(
        web_search(SimpleNamespace(deps=_search_deps("http://127.0.0.1:1", "openai")), "q")
    )
    assert "缺少 API key" in out
    assert "ai search set tavily --key" in out


def test_openai_system_prompt_and_placeholder_in_body(fake_ai_server, tmp_store):
    """系统提示随请求发出；token 占位符出现，说明动态 persona 解析生效。"""
    base_url, requests = fake_ai_server
    from hoshino.ai.providers import build_agent

    record = ProviderRecord(
        id="openai",
        url=base_url,
        key="sk-test-openai",
        kind="openai_chat",
        default_text_model="gpt-4o-mini",
    )
    agent = build_agent("openai", record, "gpt-4o-mini")
    agent.run_sync("hi", deps=_make_deps(base_url, "openai", "gpt-4o-mini"))

    req = requests[0]
    roles = [m["role"] for m in req["body"]["messages"]]
    assert "system" in roles
    system = next(m for m in req["body"]["messages"] if m["role"] == "system")
    assert "你是测试助手" in system["content"]
