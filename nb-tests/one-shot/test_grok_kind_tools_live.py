"""grok provider 两种 kind（openai_responses / openai_chat）工具调用行为对比 live 探针。

运行：

    ONE_SHOT_LIVE=1 .venv/bin/python -m pytest nb-tests/one-shot/test_grok_kind_tools_live.py -s -q

背景：18:26 的线上 turn 用 ``grok`` provider（当时 kind=openai_responses）问
腰酸背疼，1 step、0 tool call，把一句「先查一下…」的前言当最终回复发出；18:34
改用 openai_chat 后同一问题正常联网检索（4 step、11 tool call）。本探针用同一
provider url/key、同一问题，分别以两种 kind 构建真实 agent（同一 system prompt
与工具集），并抓取 provider 原始响应体，对比模型是否真的发起 function_call、
以及解析出的 ModelResponse parts。

**实测结论**：与 kind 无关，是模型偶发行为。openai_chat 常把预告写进 ``content``
（``reasoning_content`` 另有思考、``tool_calls`` 为空）；openai_responses 常夹带未请求
的原生 ``web_search_call``，同条 ``message`` 会被框架当思考清掉。chat 现用
``TextOutput(guard_reply)`` 打回预告。两种 kind 都需重跑几次才能判断倾向。

只读 aichat.db 的 grok provider 行（key 不打印）；结果打印 stdout，不落库。
"""

from __future__ import annotations

import json
import os
from typing import Any
from unittest.mock import patch

import httpx
import pytest
from _live import build_agent, build_deps, load_config

pytestmark = [
    pytest.mark.skipif(
        not os.environ.get("ONE_SHOT_LIVE"),
        reason="联网探针：设置 ONE_SHOT_LIVE=1 才运行",
    ),
]

PROBE_SCOPE = "probe:grok-kind"
QUESTION = "腰酸背疼，要什么时候去锻炼身体，怎么判断是不是急性期"
MODEL = "grok-4.6"
KINDS = ("openai_responses", "openai_chat")


def _grok_record(kind: str) -> Any:
    """真实 grok provider 行 + 覆写 kind（key 只在内存使用）。"""
    from hoshino.ai import store
    from hoshino.ai.provider import ProviderRecord

    for row in store.list_provider_rows():
        if row["id"].lower() == "grok":
            return ProviderRecord.from_row({**row, "kind": kind})
    pytest.skip("grok provider 未配置")


def _capture_raw(response_bodies: list[dict]) -> Any:
    """包装 ``models._build_http_client``，把 provider 原始响应体收进列表。"""
    from hoshino.ai import models

    async def on_response(response: httpx.Response) -> None:
        await response.aread()
        url = str(response.url)
        if "/responses" in url or "/chat/completions" in url:
            response_bodies.append(
                {"url": url, "status": response.status_code, "body": response.text}
            )

    original_build = models._build_http_client

    def build(proxy: str | None) -> httpx.AsyncClient:
        client = original_build(proxy)
        client.event_hooks.setdefault("response", []).append(on_response)
        return client

    return patch.object(models, "_build_http_client", build)


def _raw_summary(body: str) -> list[str]:
    """原始响应体的 item/choice 类型摘要（不打印思考正文）。"""
    try:
        data = json.loads(body)
    except ValueError:
        return [f"<非 JSON: {body[:80]!r}>"]
    if isinstance(data.get("output"), list):
        summary = []
        for item in data["output"]:
            kind = item.get("type")
            if kind == "function_call":
                summary.append(f"function_call({item.get('name')})")
            elif kind == "reasoning":
                texts = [block.get("text") or "" for block in (item.get("summary") or [])]
                summary.append(
                    f"reasoning(summary={len(texts)} chars={sum(len(t) for t in texts)})"
                )
            elif kind == "message":
                texts = []
                for content in item.get("content") or []:
                    if isinstance(content, dict) and content.get("type") == "output_text":
                        texts.append(content.get("text") or "")
                joined = "".join(texts)
                summary.append(f"message(text={len(joined)}字 preview={joined[:80]!r})")
            elif kind == "web_search_call":
                action = item.get("action") or {}
                summary.append(
                    f"web_search_call(status={item.get('status')} query={action.get('query')!r})"
                )
            else:
                summary.append(str(kind))
        return summary
    choices = data.get("choices") or []
    if choices:
        message = choices[0].get("message") or {}
        calls = [call.get("function", {}).get("name") for call in (message.get("tool_calls") or [])]
        return [
            f"content={bool(message.get('content'))}",
            f"reasoning_content={bool(message.get('reasoning_content'))}",
            f"tool_calls={calls}",
        ]
    return [f"keys={sorted(data)[:8]}"]


async def _ask(kind: str) -> dict[str, Any]:
    from pydantic_ai.usage import UsageLimits

    from hoshino.ai import runner

    config = load_config()
    record = _grok_record(kind)
    deps = build_deps(config, "grok", MODEL, PROBE_SCOPE)
    response_bodies: list[dict] = []
    run_log = runner.RunLog()
    result = None
    error = ""
    with _capture_raw(response_bodies):
        agent = build_agent(config, "grok", record, MODEL)
        try:
            result = await runner.run_agent_with_retry(
                agent,
                QUESTION,
                deps=deps,
                message_history=[],
                usage_limits=UsageLimits(request_limit=12),
                run_log=run_log,
            )
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
    parts: list[str] = []
    for message in result.new_messages() if result else []:
        for part in message.parts:
            name = type(part).__name__
            if name == "ThinkingPart":
                raw_content = (part.provider_details or {}).get("raw_content") or []
                parts.append(
                    f"thinking(content={len(part.content or '')}字, raw={sum(len(x) for x in raw_content)}字)"
                )
            elif name == "ToolCallPart":
                parts.append(f"tool_call({part.tool_name})")
            elif name == "TextPart":
                parts.append(f"text({len(part.content)}字)")
    return {
        "kind": kind,
        "steps": run_log.steps,
        "reason": run_log.reason,
        "tools": [call["name"] for call in run_log.tool_calls],
        "output": (result.output if result else "") or "",
        "error": error,
        "parts": parts,
        "raw": [_raw_summary(entry["body"]) for entry in response_bodies],
        "raw_keys": [
            sorted(json.loads(entry["body"]))[:12]
            if entry["body"].lstrip().startswith("{")
            else ["<non-json>"]
            for entry in response_bodies
        ],
    }


async def test_grok_two_kinds_tool_calling():
    """两种 kind 各跑一次真实问答，打印工具调用、原始响应 item 与最终回复。"""
    outcomes = [await _ask(kind) for kind in KINDS]
    for outcome in outcomes:
        print(f"\n===== kind={outcome['kind']} =====")
        print(f"steps={outcome['steps']} reason={outcome['reason']} tools={outcome['tools']}")
        if outcome["error"]:
            print(f"error={outcome['error']}")
        print(f"parts={outcome['parts']}")
        for index, (summary, keys) in enumerate(
            zip(outcome["raw"], outcome["raw_keys"], strict=True)
        ):
            print(f"raw[{index}]: {summary} keys={keys}")
        print(f"output[:200]={outcome['output'][:200]!r}")
    for outcome in outcomes:
        if not outcome["tools"]:
            print(f"\n[记录] kind={outcome['kind']} 只回了预告文本、未发起 function_call")
    assert all(outcome["output"] for outcome in outcomes), "两种 kind 都没有产出文本"
