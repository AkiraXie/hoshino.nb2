"""AI provider DB 层测试：三张新表 CRUD 与 aichat.json → DB 迁移。

store 层测试不启动 NoneBot；``tmp_store`` 把 store.engine/Session 指向临时 SQLite。
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _tmp_store(tmp_store):
    return tmp_store


# ------------------------------------------------------------ provider rows


def test_provider_row_upsert_and_get(tmp_store):
    tmp_store.upsert_provider_row(
        provider_id="deepseek",
        url="https://api.deepseek.com/anthropic",
        key="sk-test",
        kind="anthropic",
        default_text_model="deepseek-v4-flash",
    )
    row = tmp_store.get_provider_row("deepseek")
    assert row["kind"] == "anthropic"
    assert row["default_text_model"] == "deepseek-v4-flash"
    assert row["default_vision_model"] == ""
    assert tmp_store.has_provider_row("deepseek")
    assert not tmp_store.has_provider_row("ghost")


def test_provider_row_upsert_updates_existing(tmp_store):
    tmp_store.upsert_provider_row(provider_id="p", default_text_model="a")
    tmp_store.upsert_provider_row(provider_id="p", default_text_model="b", kind="openai_responses")
    row = tmp_store.get_provider_row("p")
    assert row["default_text_model"] == "b"
    assert row["kind"] == "openai_responses"


def test_provider_row_delete_removes_models(tmp_store):
    tmp_store.upsert_provider_row(provider_id="p", default_text_model="m")
    tmp_store.upsert_provider_model("p", "m", "text")
    assert tmp_store.delete_provider_row("p") is True
    assert not tmp_store.has_provider_row("p")
    assert tmp_store.list_provider_models("p") == []
    assert tmp_store.delete_provider_row("p") is False


# ------------------------------------------------------------ model-list


def test_provider_models_crud(tmp_store):
    tmp_store.upsert_provider_model("p", "text-model", "text")
    tmp_store.upsert_provider_model("p", "vision-model", "multimodal")
    tmp_store.upsert_provider_model("p", "both-model", "both")
    models = tmp_store.list_provider_models("p")
    assert {m["model"] for m in models} == {"text-model", "vision-model", "both-model"}
    by_name = {m["model"]: m["capabilities"] for m in models}
    assert by_name["vision-model"] == "multimodal"
    assert tmp_store.get_provider_model("p", "text-model")["capabilities"] == "text"
    assert tmp_store.delete_provider_model("p", "text-model") is True
    assert tmp_store.get_provider_model("p", "text-model") is None
    assert tmp_store.delete_provider_model("p", "text-model") is False


# ------------------------------------------------------------ scope models


def test_resolve_models_inherit_and_override(tmp_store):
    """双模型解析：scope 覆盖 > provider 默认；none 显式禁用 vision。"""
    from hoshino.ai import provider as provider_domain

    tmp_store.upsert_provider_row(
        provider_id="p",
        kind="openai_chat",
        default_text_model="text-default",
        default_vision_model="vision-default",
    )
    # 无覆盖 → 继承 provider 默认
    assert provider_domain.resolve_models("scope:1", "p") == (
        "text-default",
        "vision-default",
    )
    # scope 覆盖 text，vision 继承
    tmp_store.set_scope_model_override("scope:1", "text", "text-override")
    assert provider_domain.resolve_models("scope:1", "p")[0] == "text-override"
    assert provider_domain.resolve_models("scope:1", "p")[1] == "vision-default"
    # none 显式禁用 vision（provider 默认非空也被关掉）
    tmp_store.set_scope_model_override("scope:1", "vision", "none")
    assert provider_domain.resolve_models("scope:1", "p")[1] == ""
    # provider 不存在 → 双空
    assert provider_domain.resolve_models("scope:1", "ghost") == ("", "")


def test_fetch_available_models_openai(fake_ai_server):
    """fetch_available_models：GET {url}/models + Bearer 鉴权，返回排序后的 id 列表。"""
    import asyncio

    from hoshino.ai.provider import ProviderRecord, fetch_available_models

    base_url, requests = fake_ai_server
    record = ProviderRecord(id="openai", url=base_url, key="sk-test", kind="openai_chat")
    models = asyncio.run(fetch_available_models(record, verify=False))
    assert models == ["gpt-4o", "gpt-4o-mini"]  # 排序
    assert requests[0]["stem"] == "/models"
    assert requests[0]["headers"]["authorization"] == "Bearer sk-test"


def test_scope_model_override_set_and_clear(tmp_store):
    tmp_store.set_scope_model_override("scope:1", "text", "m1", updated_by="u1")
    tmp_store.set_scope_model_override("scope:1", "vision", "v1", updated_by="u1")
    assert tmp_store.get_scope_model_overrides("scope:1") == {
        "text_model": "m1",
        "vision_model": "v1",
    }
    # 清单槽
    assert tmp_store.clear_scope_model_override("scope:1", "text") is True
    assert tmp_store.get_scope_model_overrides("scope:1") == {
        "text_model": "",
        "vision_model": "v1",
    }
    # 清整行
    assert tmp_store.clear_scope_model_override("scope:1") is True
    assert tmp_store.get_scope_model_overrides("scope:1") == {
        "text_model": "",
        "vision_model": "",
    }
    # 无覆盖时返回 False
    assert tmp_store.clear_scope_model_override("scope:1") is False


# ------------------------------------------------------------ JSON 迁移


# ------------------------------------------------------------ AIConfig env 挂载


def _chat_model():
    from hoshino.ai import providers
    from hoshino.ai.provider import ProviderRecord

    before = len(providers._http_clients)
    record = ProviderRecord(id="fake", url="http://fake", key="sk-test", kind="openai_chat")
    model = providers.build_model(record, "deepseek-v4-flash")
    return model, before


def _close_build_clients(before_count: int) -> None:
    """只关闭本用例新建的 http client。

    同步测试无 running loop，``clear_agent_cache`` 的 ``create_task`` 不会执行；
    与 ``test_ai_chat.py::test_build_model_ignores_env_proxy`` 同做法，显式
    ``asyncio.run`` 关闭。只处理 ``before_count`` 之后新增的 client，避免关闭
    其他测试经 build_agent 缓存仍在使用的 client（否则后续用例请求报
    "client has been closed"）。
    """
    import asyncio

    from hoshino.ai.providers import _http_clients

    for client in _http_clients[before_count:]:
        asyncio.run(client.aclose())
    del _http_clients[before_count:]


def _completion_with(function_call: dict | None, *, tool_calls: list | None = None):
    from openai.types.chat import ChatCompletion

    message: dict = {
        "role": "assistant",
        "content": "正常回复" if not tool_calls else None,
        "function_call": function_call,
        "tool_calls": tool_calls,
    }
    return ChatCompletion.model_construct(
        id="chatcmpl-fake",
        object="chat.completion",
        created=1,
        model="deepseek-v4-flash",
        choices=[
            {
                "index": 0,
                "message": message,
                "finish_reason": "tool_calls" if tool_calls else "stop",
            }
        ],
    )


def test_openai_chat_validation_tolerates_empty_function_call_placeholder():
    """``_validate_completion`` 面对网关畸形 function_call 的整体行为。

    opencode-go 等 OpenAI 兼容网关在每条响应里附加空占位 legacy function_call
    （name/arguments 均为 null），pydantic-ai 严格校验会拒绝整个响应，导致每轮
    对话失败。验证解析层整体行为：
    - 纯文本响应：空占位被归一化为 None，校验通过，正常文本可用；
    - 工具调用响应：占位移除后真实 tool_calls 保留，不影响工具链路；
    - 半空占位（name null 但 arguments 有值）不属于网关占位形态，仍抛
      ``UnexpectedModelBehavior`` 且异常携带原始响应体（失败日志可定位）。
    """
    from pydantic_ai.exceptions import UnexpectedModelBehavior

    from hoshino.ai.errors import format_exception_detail

    model, close_clients = _chat_model()
    try:
        # 纯文本：空占位不阻断回复
        text_response = _completion_with({"name": None, "arguments": None})
        validated = model._validate_completion(text_response)
        assert validated.choices[0].message.function_call is None

        # 工具调用：占位移除后 tool_calls 原样保留
        tool_response = _completion_with(
            {"name": None, "arguments": None},
            tool_calls=[
                {
                    "id": "call-1",
                    "type": "function",
                    "function": {"name": "now", "arguments": "{}"},
                }
            ],
        )
        validated = model._validate_completion(tool_response)
        message = validated.choices[0].message
        assert message.function_call is None
        assert message.tool_calls[0].function.name == "now"

        # 非占位畸形（仍校验失败）：异常带原始响应体，失败日志可输出
        partial = _completion_with({"name": None, "arguments": "{}"})
        with pytest.raises(UnexpectedModelBehavior) as exc_info:
            model._validate_completion(partial)
        exc = exc_info.value
        assert exc.body is not None
        assert '"function_call"' in exc.body
        detail = format_exception_detail(exc)
        assert "function_call" in detail
        assert "Input should be a valid string" in detail
    finally:
        _close_build_clients(close_clients)
