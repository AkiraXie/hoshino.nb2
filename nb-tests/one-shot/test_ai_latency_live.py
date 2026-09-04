"""AI 延迟 live 测试：非流式完整轮 vs 流式 TTFB 对照。

运行：

    ONE_SHOT_LIVE=1 uv run pytest nb-tests/one-shot/test_ai_latency_live.py -s -q

问题在 fixtures/ai_latency.json。两段测量：

1. 非流式：``run_agent_with_retry`` 完整轮，拿到逐步 duration（DEBUG 日志的
   ``AI step N ...`` 行同步可见）；
2. 流式对照：逐 ModelRequestNode 走 ``node.stream`` 手动推进图（与 runner 流式
   分支同驱动方式），测每步 TTFB 与总耗时。

两段都要真实跑一轮，预算较大；报告落 agent-plan-report/ai-latency-probe.md。
"""

from __future__ import annotations

import asyncio
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
    make_probe_logger,
    print_step_details,
    write_report,
)

pytestmark = [
    pytest.mark.skipif(
        not os.environ.get("ONE_SHOT_LIVE"),
        reason="联网探针：设置 ONE_SHOT_LIVE=1 才运行",
    ),
]

PROBE_SCOPE = "probe:ai-latency"
_FIXTURE = load_fixture("ai_latency")


async def _run_streaming(agent: Any, deps: Any, config: Any) -> dict[str, Any]:
    """流式对照：逐 ModelRequestNode 走 node.stream，测每步 TTFB 与总耗时。

    TTFB 取「进入 stream 后首个事件到达」的墙钟（客户端视角近似，不含本地
    请求准备）。直驱节点没有 runner 的「收尾指令」护栏，模型工具调用偏多时会
    自然超过 chat 上限；这里只测 TTFB，预算放宽一倍保证跑完整轮。
    """
    from pydantic_ai.usage import UsageLimits
    from pydantic_graph import End

    from hoshino.ai import metrics

    started = time.perf_counter()
    ttfb: list[float] = []
    step_times: list[float] = []
    steps = 0
    async with agent.iter(
        _FIXTURE["question"],
        deps=deps,
        message_history=[],
        usage_limits=UsageLimits(request_limit=config.chat_max_requests * 2),
    ) as agent_run:
        node = agent_run.next_node
        while not isinstance(node, End):
            if type(node).__name__ == "ModelRequestNode":
                steps += 1
                step_start = time.perf_counter()
                first_chunk_at = None
                async with node.stream(agent_run.ctx) as stream:
                    async for _ in stream:
                        if first_chunk_at is None:
                            first_chunk_at = time.perf_counter() - step_start
                step_times.append(time.perf_counter() - step_start)
                ttfb.append(first_chunk_at if first_chunk_at is not None else 0.0)
                # stream 只设置节点结果，图推进需显式调用（与 runner 流式分支一致）。
                node = await agent_run._advance_graph(node)
            else:
                node = await agent_run.next(node)
        result = agent_run.result
        usage = metrics.snapshot_from_result(result)
    return {
        "elapsed": time.perf_counter() - started,
        "steps": steps,
        "ttfb": ttfb,
        "step_times": step_times,
        "usage": usage,
    }


async def test_non_stream_then_stream_ttfb():
    """非流式完整轮 + 流式 TTFB 对照；断言非流式成功，流式结果仅记录。"""
    from pydantic_ai.usage import UsageLimits

    from hoshino.ai import metrics, provider, runner

    enable_debug_logging()
    config = load_config()
    provider_id, model = provider.resolve_model(PROBE_SCOPE)
    assert provider_id and model, "未配置默认模型，请超级用户 `ai model default`"
    record = provider.get_provider(provider_id)
    assert record is not None, f"provider `{provider_id}` 不存在于 aichat.db"

    deps = build_deps(config, provider_id, model, PROBE_SCOPE)
    agent = build_agent(config, provider_id, record, model)

    print("=" * 70)
    print("AI 延迟 live 探针（DEBUG 日志已开启）")
    print(f"provider={provider_id} kind={record.kind} url={record.url}")
    print(f"model={model}")
    print(
        f"web_fetch_max_chars={config.web_fetch_max_chars} summarize={config.web_fetch_summarize}"
    )
    print(
        f"compaction_window_tokens={config.compaction_window_tokens} "
        f"stream_requests={config.stream_requests}"
    )
    print(f"问题：{_FIXTURE['question']}")
    print("=" * 70)

    # 1. 非流式完整轮
    run_log = runner.RunLog()
    started = time.perf_counter()
    try:
        result = await asyncio.wait_for(
            runner.run_agent_with_retry(
                agent,
                _FIXTURE["question"],
                deps=deps,
                message_history=[],
                usage_limits=UsageLimits(request_limit=config.chat_max_requests),
                run_log=run_log,
                on_event=make_probe_logger(),
            ),
            timeout=config.chat_run_timeout_seconds,
        )
    except Exception as exc:
        elapsed = time.perf_counter() - started
        raise AssertionError(f"非流式跑挂（{elapsed:.1f}s）：{type(exc).__name__}: {exc}") from exc
    elapsed = time.perf_counter() - started

    usage = metrics.snapshot_from_result(result)
    print(
        f"\n[OK] 耗时={elapsed:.1f}s steps={run_log.steps} "
        f"tokens={usage.total_tokens}（in {usage.request_tokens} / out {usage.response_tokens}）"
    )
    print(f"工具调用：{[t['name'] for t in run_log.tool_calls] or '无'}")
    print_step_details(run_log)
    print(f"回复（前 300 字）：{result.output[:300]}")

    # 2. 流式 TTFB 对照（测量性质：失败仅记录，不判测试失败）
    streamed: dict[str, Any] | None = None
    try:
        streamed = await _run_streaming(agent, deps, config)
    except Exception as exc:
        print(f"\n[流式对照失败] {type(exc).__name__}: {exc}")

    if streamed is not None:
        print(f"\n流式：总 {streamed['elapsed']:.1f}s / {streamed['steps']} 步")
        for i, (t, s) in enumerate(zip(streamed["ttfb"], streamed["step_times"], strict=True), 1):
            print(f"  step {i}: TTFB={t:.2f}s 全步={s:.1f}s")

    write_report(
        "ai-latency-probe.md",
        [
            "# AI 延迟 live 探针报告",
            "",
            f"- 时间：{time.strftime('%Y-%m-%d %H:%M')}",
            f"- provider：`{provider_id}/{model}`；问题：{_FIXTURE['question']}",
            f"- 非流式：{elapsed:.1f}s / {run_log.steps} steps / "
            f"tokens {usage.total_tokens}（in {usage.request_tokens} / out {usage.response_tokens}）",
            (
                f"- 流式：总 {streamed['elapsed']:.1f}s；"
                + "；".join(f"TTFB {t:.2f}s" for t in streamed["ttfb"])
                if streamed is not None
                else "- 流式：对照跑挂（见控制台）"
            ),
            "",
            "注：本文不含任何 key/token，密钥仅存在于 aichat.db",
        ],
    )
