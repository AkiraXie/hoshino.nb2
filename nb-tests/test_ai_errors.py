"""``errors.format_exception_detail`` 与 ``runner.tool_calls_from_node`` 单元测试。

失败日志可观测性（error=UnexpectedModelBehavior 等只显示类名）的修复保障：
- 异常详情必须包含 pydantic-ai 异常的 message / body / status / tool 字段；
- 未知异常回退 str/repr，长 body 截断，ExceptionGroup 聚合子异常；
- 图节点工具名提取 duck-typed，非 CallToolsNode 返回空列表。
"""

from __future__ import annotations

import builtins

import pytest
from pydantic_ai.exceptions import ModelHTTPError, UnexpectedModelBehavior

from hoshino.ai.errors import format_exception_detail
from hoshino.ai.runner import tool_calls_from_node


def _make_group(*exceptions: BaseException) -> BaseException:
    """跨版本构造 ExceptionGroup：3.11+ 用内置，3.10 用 exceptiongroup 回退包。"""
    group_cls = getattr(builtins, "BaseExceptionGroup", None)
    if group_cls is None:
        # 3.11 以下回退包；别名与上方 group_cls 保持一致（本项目 Python>=3.12，该分支不执行）。
        from exceptiongroup import BaseExceptionGroup as group_cls  # type: ignore  # noqa: N813

    return group_cls("group", exceptions)


# ----------------------------------------------------------- format_exception_detail


def test_format_umb_includes_message_and_body():
    exc = UnexpectedModelBehavior(
        "模型返回了非法工具调用", body='{"tool": "web_search", "args": "oops"}'
    )
    detail = format_exception_detail(exc)
    assert "模型返回了非法工具调用" in detail
    assert '"tool": "web_search"' in detail


def test_format_model_http_error_includes_status_and_body():
    exc = ModelHTTPError(429, "deepseek", body={"error": "rate limited"})
    detail = format_exception_detail(exc)
    assert "status=429" in detail
    assert "rate limited" in detail


def test_format_plain_exception_uses_str():
    assert format_exception_detail(RuntimeError("boom")) == "boom"


def test_format_empty_str_falls_back_to_repr():
    detail = format_exception_detail(TimeoutError())
    assert detail.startswith("TimeoutError")


def test_format_truncates_long_body():
    exc = UnexpectedModelBehavior("x", body="a" * 5000)
    detail = format_exception_detail(exc, limit=100)
    assert "truncated" in detail
    assert len(detail) < 200


def test_format_exception_group_aggregates_children():
    detail = format_exception_detail(_make_group(RuntimeError("a"), ValueError("b")))
    assert "a" in detail
    assert "b" in detail


def test_format_wrapped_tool_error_name():
    """ToolFailedError 类把工具名包在 .tool_failed 上，应被提取。"""

    class _Wrapped:
        tool_name = "web_search"

    class _ToolError(Exception):
        def __init__(self):
            self.tool_failed = _Wrapped()
            super().__init__("search failed")

    detail = format_exception_detail(_ToolError())
    assert "tool=web_search" in detail
    assert "search failed" in detail


# ----------------------------------------------------------- tool_calls_from_node


class CallToolsNode:
    """与 pydantic-ai 的 CallToolsNode 同名的测试替身（duck-typed 识别）。"""

    def __init__(self, parts=None):
        self.model_response = type("ModelResponse", (), {"parts": parts or []})()


def test_tool_calls_from_node_extracts_names():
    node = CallToolsNode(
        [
            type("P", (), {"tool_name": "web_search"})(),
            type("P", (), {"tool_name": "now"})(),
        ]
    )
    assert tool_calls_from_node(node) == ["web_search", "now"]


def test_tool_calls_from_node_ignores_other_nodes():
    assert tool_calls_from_node(object()) == []
    assert tool_calls_from_node(CallToolsNode([])) == []
    assert tool_calls_from_node(CallToolsNode([type("P", (), {})()])) == []


# ---------------------------------------------------- tool_call_events_from_node


def test_tool_call_events_from_node_redacts_args():
    from hoshino.ai.runner import tool_call_events_from_node

    node = CallToolsNode(
        [
            type(
                "P",
                (),
                {"tool_name": "web_search", "args": {"q": "secret-string", "n": 3}},
            )(),
            type("P", (), {"tool_name": "now"})(),
        ]
    )
    assert tool_call_events_from_node(node) == [
        {"name": "web_search", "args_summary": "{q=<13>, n=int}"},
        {"name": "now", "args_summary": "{}"},
    ]
    assert tool_call_events_from_node(object()) == []
    assert tool_call_events_from_node(CallToolsNode([])) == []


def test_redact_args_shapes():
    from hoshino.ai.runner import redact_args

    assert redact_args(None) == "{}"
    assert redact_args("abc") == "<str:3>"
    assert redact_args({"k": "vv", "n": 1}) == "{k=<2>, n=int}"
    assert redact_args(42) == "int"


# ------------------------------------------------------- 观测日志素材


def test_summarize_content_truncates_and_marks_binary():
    from hoshino.ai.runner import summarize_content

    assert summarize_content(None) == ""
    assert summarize_content("short") == "short"
    long_text = "长" * 500
    assert summarize_content(long_text).endswith("…")
    assert len(summarize_content(long_text)) <= 201
    assert summarize_content(b"\x89PNG") == "<bytes:4>"
    assert summarize_content(["a", "b"]) == "a | b"
    binary = type("BC", (), {"data": b"abc", "media_type": "image/png"})()
    assert summarize_content(binary) == "<image/png:3B>"


def test_last_message_summary_extracts_parts():
    from types import SimpleNamespace

    from pydantic_ai.messages import (
        ModelRequest,
        RetryPromptPart,
        ToolReturnPart,
        UserPromptPart,
    )

    from hoshino.ai.runner import _last_message_summary

    user_state = SimpleNamespace(
        message_history=[ModelRequest(parts=[UserPromptPart(content="你好")])]
    )
    assert "user: 你好" in _last_message_summary(user_state)

    tool_state = SimpleNamespace(
        message_history=[
            ModelRequest(
                parts=[ToolReturnPart(tool_name="web_search", content="搜索结果 " + "x" * 300)]
            )
        ]
    )
    summary = _last_message_summary(tool_state)
    assert "tool web_search →" in summary
    assert summary.endswith("…")  # 长结果截断

    retry_state = SimpleNamespace(
        message_history=[ModelRequest(parts=[RetryPromptPart(content="参数不合法")])]
    )
    assert "retry: 参数不合法" in _last_message_summary(retry_state)

    assert _last_message_summary(SimpleNamespace(message_history=[])) == ""
    assert _last_message_summary(SimpleNamespace()) == ""


def test_response_introspection_extracts_thinking_and_text():
    from types import SimpleNamespace

    from pydantic_ai.messages import TextPart, ThinkingPart

    from hoshino.ai.runner import _response_introspection

    node = SimpleNamespace(
        model_response=SimpleNamespace(
            parts=[ThinkingPart(content="先查一下再答"), TextPart(content="我用工具")]
        )
    )
    intro = _response_introspection(node)
    assert "先查一下再答" in intro
    assert "我用工具" in intro
    assert _response_introspection(SimpleNamespace(model_response=None)) == ""
    assert _response_introspection(object()) == ""


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-q"])
