"""DeepSeek 端点×优化开关 延迟矩阵 live 测试。

运行：

    ONE_SHOT_LIVE=1 uv run pytest nb-tests/one-shot/test_deepseek_matrix_live.py -s -q
    # 快速档（每实验最多 4 次请求）：ONE_SHOT_LIVE=1 ONE_SHOT_QUICK=1 uv run pytest ...

对 aichat.db 的 deepseek provider（key 从 DB 只读），在 anthropic / openai_responses
两种端点 × 优化前后（web_fetch_max_chars / summarize / compaction_window /
tool_result_spill 各参数）各跑一轮「问题 → 工具 → 答案」，对比总耗时与逐步
明细。实验矩阵是测量性质：断言至少一个实验成功，其余失败仅记录。
报告落 agent-plan-report/matrix-deepseek-latency.md。
"""

from __future__ import annotations

import asyncio
import dataclasses
import os
import time
from typing import Any

import pytest
from _live import (
    build_agent,
    build_deps,
    enable_debug_logging,
    load_config,
    load_fixture,
    write_report,
)

pytestmark = [
    pytest.mark.skipif(
        not os.environ.get("ONE_SHOT_LIVE"),
        reason="联网探针：设置 ONE_SHOT_LIVE=1 才运行",
    ),
]

PROBE_SCOPE = "probe:matrix-live"
_FIXTURE = load_fixture("deepseek_matrix")
# 实验 key：url 路径端点 → (endpoint 名, AIConfig 改写)。
_EXPERIMENTS: dict[str, tuple[str, dict[str, Any]]] = {
    "anthropic": (
        "anthropic",
        {},  # 优化后（默认配置）
    ),
    "anthropic_baseline": (
        "anthropic",
        {
            "web_fetch_max_chars": 50_000,
            "web_fetch_summarize": False,
            "compaction_window_tokens": 0,
            "tool_result_spill_max_chars": 0,
        },
    ),
    "responses": (
        "openai_responses",
        {},
    ),
    "responses_baseline": (
        "openai_responses",
        {
            "web_fetch_max_chars": 50_000,
            "web_fetch_summarize": False,
            "compaction_window_tokens": 0,
            "tool_result_spill_max_chars": 0,
        },
    ),
}


def _load_deepseek_key() -> str | None:
    """只读 provider key（不打印）。"""
    from hoshino.ai import store

    for row in store.list_provider_rows():
        if row["id"].lower() == "deepseek" and row.get("key"):
            return row["key"]
    return None


def _build_record(kind: str, base_url: str) -> Any:
    """按端点构造 ProviderRecord（deepseek key 走 DB）。"""
    from hoshino.ai.provider import ProviderRecord

    return ProviderRecord(
        id="deepseek",
        url=base_url,
        kind=kind,
        key=_load_deepseek_key() or "",
        timeout_seconds=120.0,
    )


async def _record_one(
    experiment_key: str, endpoint: str, config: Any, question: str
) -> dict[str, Any]:
    """跑一个实验：与 chat 同链路（重试护栏 + run_log + 护栏上限）。"""
    from pydantic_ai.usage import UsageLimits

    from hoshino.ai import metrics, runner

    base_url = (
        "https://api.deepseek.com/anthropic"
        if endpoint == "anthropic"
        else "https://api.deepseek.com"
    )
    model = _FIXTURE["model"]
    record = _build_record(endpoint, base_url)
    cfg = dataclasses.replace(config, **_EXPERIMENTS[experiment_key][1])
    deps = build_deps(cfg, "deepseek", model, PROBE_SCOPE)
    agent = build_agent(cfg, "deepseek", record, model)

    run_log = runner.RunLog()
    started = time.perf_counter()
    try:
        result = await asyncio.wait_for(
            runner.run_agent_with_retry(
                agent,
                question,
                deps=deps,
                message_history=[],
                usage_limits=UsageLimits(
                    request_limit=8 if os.environ.get("ONE_SHOT_QUICK") else cfg.chat_max_requests
                ),
                run_log=run_log,
            ),
            timeout=cfg.chat_run_timeout_seconds,
        )
    except Exception as exc:
        return {
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}",
            "elapsed": time.perf_counter() - started,
        }

    usage = metrics.snapshot_from_result(result)
    return {
        "ok": True,
        "text": result.output,
        "elapsed": time.perf_counter() - started,
        "steps": run_log.steps,
        "usage": usage,
        "tools": list(run_log.tool_calls),
    }


async def test_endpoint_optimization_matrix():
    """四个实验逐个跑；断言至少一个成功，矩阵打印到 stdout 并落报告。"""

    enable_debug_logging()
    assert _load_deepseek_key(), "deepseek provider 未配置或缺少 key（aichat.db）"
    config = load_config()
    question = _FIXTURE["question"]

    results: dict[str, dict[str, Any]] = {}
    for key in _EXPERIMENTS:
        endpoint = _EXPERIMENTS[key][0]
        tag = "优化前" if key.endswith("_baseline") else "优化后"
        print(f"\n{'=' * 70}\n== {key}（{endpoint} / {tag}）==", flush=True)
        started = time.perf_counter()
        results[key] = await _record_one(key, endpoint, config, question)
        res = results[key]
        if res["ok"]:
            usage = res["usage"]
            print(
                f"✅ [{res['elapsed']:.1f}s] steps={res['steps']} tokens={usage.total_tokens}"
                f"（in {usage.request_tokens} / out {usage.response_tokens}）"
            )
            print(f"工具调用：{[t['name'] for t in res['tools']] or '无'}")
            print(f"回复（前 200 字）：{res['text'][:200]}")
        else:
            print(f"❌ [{time.perf_counter() - started:.1f}s] {res['error']}")

    assert any(r["ok"] for r in results.values()), "四个实验全部失败"

    lines = [
        "# DeepSeek 端点延迟矩阵 live 探针",
        "",
        f"- 时间：{time.strftime('%Y-%m-%d %H:%M')}",
        "",
    ]
    for key, res in results.items():
        if res["ok"]:
            lines.append(f"## {key}（✅ {res['elapsed']:.1f}s / {res['steps']} steps）")
        else:
            lines.append(f"## {key}（❌ {res['elapsed']:.1f}s：{res['error']}）")
        lines += ["", "注：本文不含任何 key/token，密钥仅存在于 aichat.db", ""]
    write_report("matrix-deepseek-latency.md", lines)
