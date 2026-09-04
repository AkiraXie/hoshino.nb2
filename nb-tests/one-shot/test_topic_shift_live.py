"""话题切换 live 测试：验证 topic-shift 检测对历史处理的真实链路。

运行：

    ONE_SHOT_LIVE=1 uv run pytest nb-tests/one-shot/test_topic_shift_live.py -s -q

两轮对话：Q1 建立技术话题历史 → Q2 切换到明日方舟。Q2 走
``context.prepare_history`` 的真实话题检测路径，观察历史消息数变化与
回复质量；两轮的实时节点明细（msgs/parts/text_chars + 工具调用）打印到
stdout。fixtures/topic_shift.json 持有两问；结束后清理 probe scope memory。
"""

from __future__ import annotations

import asyncio
import os
import time
from typing import Any

import pytest
from _live import build_agent, build_deps, load_config, load_fixture, write_report

pytestmark = [
    pytest.mark.skipif(
        not os.environ.get("ONE_SHOT_LIVE"),
        reason="联网探针：设置 ONE_SHOT_LIVE=1 才运行",
    ),
]

PROBE_SCOPE = "probe:topic-shift"
_FIXTURE = load_fixture("topic_shift")


def _print_event(ev: Any) -> None:
    """实时打印每步 model request 规模与工具调用（话题切换观测重点）。"""
    node = ev.node
    name = type(node).__name__
    state = getattr(ev.ctx, "state", None)
    history = getattr(state, "message_history", None) or []
    if name != "ModelRequestNode":
        return
    total_chars = 0
    total_parts = 0
    for msg in history:
        parts = getattr(msg, "parts", []) or []
        total_parts += len(parts)
        for part in parts:
            content = getattr(part, "content", None)
            if isinstance(content, str):
                total_chars += len(content)
            elif isinstance(content, list):
                total_chars += sum(len(x) for x in content if isinstance(x, str))
            elif type(part).__name__ == "ToolCallPart":
                args = getattr(part, "args", None)
                if args:
                    total_chars += len(str(args))
    print(f"  📤 ModelRequest: msgs={len(history)} parts={total_parts} text_chars={total_chars:,}")
    if history:
        for part in getattr(history[-1], "parts", []):
            ptype = type(part).__name__
            content = getattr(part, "content", None)
            if isinstance(content, str):
                preview = content[:120] + ("..." if len(content) > 120 else "")
                print(f"    last_msg {ptype}: {preview}")
            elif ptype == "ToolReturnPart":
                tool = getattr(part, "tool_name", "?")
                text = content if isinstance(content, str) else ""
                preview = text[:100] + ("..." if len(text) > 100 else "")
                print(f"    last_msg ToolReturn({tool}): {preview}")


async def _ask_with_history(
    agent: Any, deps: Any, question: str, history: list, config: Any, label: str
) -> dict[str, Any]:
    """带历史的单轮对话，打印话题检测前后的历史规模与每步详情。"""
    from pydantic_ai.usage import UsageLimits

    from hoshino.ai import context, metrics, runner

    processed = context.prepare_history(PROBE_SCOPE, history, config, new_question=question)
    print(f"\n{'=' * 70}\n[{label}] {question}")
    print(f"话题检测后历史消息数：{len(processed)}（原 {len(history)}）")

    run_log = runner.RunLog()
    started = time.perf_counter()
    try:
        result = await asyncio.wait_for(
            runner.run_agent_with_retry(
                agent,
                question,
                deps=deps,
                message_history=processed,
                usage_limits=UsageLimits(request_limit=config.chat_max_requests),
                run_log=run_log,
                on_event=_print_event,
            ),
            timeout=config.chat_run_timeout_seconds,
        )
    except Exception as exc:
        elapsed = time.perf_counter() - started
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}", "elapsed": elapsed}

    elapsed = time.perf_counter() - started
    usage = metrics.snapshot_from_result(result)
    print(
        f"  ✅ [{elapsed:.1f}s] steps={run_log.steps} "
        f"tokens={usage.total_tokens}(in={usage.request_tokens}/out={usage.response_tokens})"
    )
    print(f"  回复: {result.output[:200]}{'...' if len(result.output) > 200 else ''}")
    return {
        "ok": True,
        "text": result.output,
        "elapsed": elapsed,
        "steps": run_log.steps,
        "usage": usage,
        "new_messages": runner.result_new_messages(result, processed),
    }


def _cleanup_memory() -> None:
    from hoshino.ai import store

    for key in store.memory_list_keys(PROBE_SCOPE):
        store.memory_delete(PROBE_SCOPE, key)


async def test_topic_shift_two_turns():
    """Q1 建立历史 → Q2 话题切换；断言两轮成功并打印检测效果。"""
    from hoshino.ai import provider

    config = load_config()
    provider_id = config.default
    record = provider.get_provider(provider_id)
    assert record is not None, f"provider `{provider_id}` 不存在于 aichat.db"
    model = provider.resolve_text_model(PROBE_SCOPE, provider_id)
    if isinstance(model, tuple):
        _, model = model
    assert model, f"provider `{provider_id}` 未配置文本模型"

    print(
        f"provider={provider_id} model={model} topic_shift_detection={config.topic_shift_detection}"
    )
    deps = build_deps(config, provider_id, model, PROBE_SCOPE)
    agent = build_agent(config, provider_id, record, model)

    try:
        r1 = await _ask_with_history(
            agent, deps, _FIXTURE["setup_question"], [], config, "Q1 无历史"
        )
        assert r1["ok"], f"Q1 失败：{r1.get('error')}"

        history_for_q2 = r1["new_messages"]
        print(f"\nQ1 产出 {len(history_for_q2)} 条新消息，将作为 Q2 的历史")
        r2 = await _ask_with_history(
            agent, deps, _FIXTURE["shift_question"], history_for_q2, config, "Q2 话题切换"
        )
        assert r2["ok"], f"Q2 失败：{r2.get('error')}"
    finally:
        _cleanup_memory()

    write_report(
        "topic-shift-live-probe.md",
        [
            "# 话题切换 live 探针报告",
            "",
            f"- 时间：{time.strftime('%Y-%m-%d %H:%M')}",
            f"- Q1：{_FIXTURE['setup_question']}（{r1['elapsed']:.1f}s / {r1['steps']} steps）",
            f"- Q2：{_FIXTURE['shift_question']}（{r2['elapsed']:.1f}s / {r2['steps']} steps；"
            f"历史 {len(history_for_q2)} 条）",
            "",
            "## Q2 回复",
            "",
            r2["text"],
            "",
            "注：本文不含任何 key/token，密钥仅存在于 aichat.db",
        ],
    )
