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
from hoshino.ai.provider import ProviderRecord
from hoshino.ai.deps import AgentDeps, PermissionSnapshot, Telemetry


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

    record = ProviderRecord(
        id="openai", url="http://127.0.0.1:1", key="k", kind="openai_chat"
    )
    agent = build_agent("openai", record, "gpt-4o-mini")

    wrappers = [t for t in agent.toolsets if isinstance(t, ApprovalRequiredToolset)]
    assert len(wrappers) == 1, "toolsets 中应有且仅有一个 ApprovalRequiredToolset"
    assert isinstance(wrappers[0].wrapped, DynamicToolset)
    assert wrappers[0].approval_required_func is not None


def test_build_agent_cached_per_provider():
    """缓存 key 含 provider_config：不同 provider 不同 agent，同 provider 复用。"""
    from hoshino.ai.providers import build_agent

    record1 = ProviderRecord(
        id="openai", url="http://127.0.0.1:1", key="k1", kind="openai_chat"
    )
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
    result = agent.run_sync(
        "你好", deps=_make_deps(base_url, "anthropic", "claude-3-5-sonnet")
    )

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


# ------------------------------------------------------------ 原生联网搜索


def _tools_in(requests: list[dict]) -> list[dict]:
    """提取最后一次请求 body 里的 tools 列表（Anthropic 格式）。"""
    return (requests[-1]["body"].get("tools") or []) if requests else []


def _native_search_tool(tools: list[dict]) -> dict | None:
    return next((t for t in tools if t.get("type") == "web_search_20250305"), None)


def test_anthropic_native_web_search_tool_in_body(fake_ai_server, tmp_store):
    """anthropic kind + 原生搜索开启：请求 tools 携带服务端 web_search_20250305。

    DeepSeek 的 ``/anthropic`` 端点用该服务端工具做联网搜索（模型侧不再需要
    duckduckgo/web_fetch 客户端抓取）。
    """
    base_url, requests = fake_ai_server
    from hoshino.ai.providers import build_agent

    record = ProviderRecord(
        id="anthropic",
        url=base_url,
        key="sk-ant-test-123",
        kind="anthropic",
        default_text_model="deepseek-v4-flash",
    )
    agent = build_agent("anthropic", record, "deepseek-v4-flash")
    agent.run_sync("你好", deps=_make_deps(base_url, "anthropic", "deepseek-v4-flash"))

    tool = _native_search_tool(_tools_in(requests))
    assert tool is not None, "anthropic 请求应携带服务端 web_search 工具"
    assert tool["name"] == "web_search"


def test_native_web_search_disabled_omits_tool(fake_ai_server, tmp_store):
    """web_search_native=False：anthropic kind 也不注入服务端 web_search 工具。"""
    base_url, requests = fake_ai_server
    from hoshino.ai.providers import build_agent

    record = ProviderRecord(
        id="anthropic",
        url=base_url,
        key="sk-ant-test-123",
        kind="anthropic",
        default_text_model="deepseek-v4-flash",
    )
    agent = build_agent(
        "anthropic", record, "deepseek-v4-flash", web_search_native=False
    )
    agent.run_sync("你好", deps=_make_deps(base_url, "anthropic", "deepseek-v4-flash"))

    assert _native_search_tool(_tools_in(requests)) is None


def test_openai_chat_no_native_web_search_tool(fake_ai_server, tmp_store):
    """openai_chat kind 不支持原生 web_search：不注入、不报错，走既有工具。"""
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
    assert _native_search_tool(_tools_in(requests)) is None


def test_anthropic_web_search_tool_result_parses(
    fake_ai_server, tmp_store, monkeypatch
):
    """服务端 web_search_tool_result 内容块可解析，最终输出取 text 块。

    DeepSeek 原生搜索的响应会在 content 里带 ``web_search_tool_result``
    （内含加密的网页内容），pydantic-ai 应跳过它并把后续 text 作为模型输出。
    """
    import json as _json

    from fake_ai_server import _FakeHandler

    base_url, requests = fake_ai_server
    from hoshino.ai.providers import build_agent

    def patched_do_post(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length)
        stem = self.path.split("?")[0]
        self.requests.append(
            {
                "path": self.path,
                "stem": stem,
                "headers": {k.lower(): v for k, v in self.headers.items()},
                "body": _json.loads(raw) if raw else {},
            }
        )
        if stem == "/v1/messages":
            self._respond(
                200,
                {
                    "id": "msg_fake_02",
                    "type": "message",
                    "role": "assistant",
                    "model": "deepseek-v4-flash",
                    "content": [
                        {
                            "type": "web_search_tool_result",
                            "content": [
                                {
                                    "type": "web_search_result",
                                    "title": "标题",
                                    "url": "https://example.com",
                                    "encrypted_content": "enc",
                                    "page_age": None,
                                }
                            ],
                        },
                        {"type": "text", "text": "查到了：今天 25 度"},
                    ],
                    "stop_reason": "end_turn",
                    "stop_sequence": None,
                    "usage": {"input_tokens": 10, "output_tokens": 5},
                },
            )
        else:
            self._respond(404, {"error": "not found"})

    monkeypatch.setattr(_FakeHandler, "do_POST", patched_do_post)

    record = ProviderRecord(
        id="anthropic",
        url=base_url,
        key="sk-ant-test-123",
        kind="anthropic",
        default_text_model="deepseek-v4-flash",
    )
    agent = build_agent("anthropic", record, "deepseek-v4-flash")
    result = agent.run_sync(
        "查天气", deps=_make_deps(base_url, "anthropic", "deepseek-v4-flash")
    )

    assert result.output == "查到了：今天 25 度"
    assert _native_search_tool(_tools_in(requests)) is not None


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
