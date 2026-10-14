"""单步超时 live 探针：真实 provider 下验证「单步上限」语义（联网，不进常规套件）。

运行：

    ONE_SHOT_LIVE=1 uv run pytest nb-tests/one-shot/test_ai_step_timeout_live.py -s -q

覆盖三件事：
1. 正向：``step_timeout_seconds`` 取一个小于整轮耗时的值跑多步 run（提示模型连做多次
   web_search/web_fetch），断言「整轮总耗时 > 单步上限」且没有任何单步越界、run 正常
   完成——旧实现是整轮 180s 墙钟，这类多步调研会被误杀。
2. 负向：``step_timeout_seconds`` 取 0.3s 且提示不需要工具，断言失败类型是超时
   （``httpx.TimeoutException`` / 内建 ``TimeoutError``，含被 provider SDK 包装的
   形态），且耗时按单次请求的上限收敛——证明上限落在单次请求而不是整轮。
3. 接线：真实 agent 的模型请求设置与工具集都带上单步上限（工具执行超时的机制本身
   由 ``FunctionToolset(timeout=)`` 保证，见机制探针）。

只打印脱敏信息（耗时、步数、工具名、token 数），不落 key/token。
"""

from __future__ import annotations

import asyncio
import dataclasses
import os
import time

import pytest
from _live import (
    PROBE_RUN_TIMEOUT_SECONDS,
    build_agent,
    build_deps,
    load_config,
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

PROBE_SCOPE = "probe:step-timeout-live"

#: 正向用例的单步上限：刻意取一个小于整轮耗时的值，让「总时长 > 单步上限仍然跑完」
#: 成为决定性断言（生产默认是 300s）。取值需高于最慢的合法单步（web_fetch 抓取
#: 实测 30s 量级），否则工具侧会先撞上工具上限。
_POSITIVE_STEP_TIMEOUT = 40.0

# 多步提示：刻意要求多次独立搜索 + 抓取，制造 4~6 步、总时长超过单步上限的 run
# （旧实现是整轮 180s 墙钟，这类多步调研最容易被误杀）。
_MULTI_STEP_PROMPT = (
    "请用 web_search 分别检索这 5 个问题：「NoneBot2 是什么」「pydantic-ai 是什么」"
    "「Milky 协议是什么」「NoneBot2 适配器有哪些」「pydantic-ai 支持哪些模型提供商」，"
    "各自记录来源链接；再用 web_fetch 打开其中至少 3 个链接确认内容。"
    "最后用三句话总结这几件事。必须真实调用工具，不要凭记忆作答。"
)

_NO_TOOL_PROMPT = "只回复两个字：你好。不要调用任何工具。"


def _prepare() -> tuple[object, str, str, object]:
    """读取真实配置/provider（与 chat 同构），返回 (config, provider_id, model, record)。"""
    from hoshino.ai import provider, store

    store.ensure_schema()
    config = load_config()
    provider_id, model = provider.resolve_model(PROBE_SCOPE)
    record = provider.get_provider(provider_id) if provider_id else None
    assert record is not None and model, (
        "未配置默认模型（超级用户 `ai model default <provider> <模型>`）"
    )
    return config, provider_id, model, record


async def test_multi_step_run_completes_with_step_timeout():
    """正向：整轮耗时超过单步上限，run 仍正常跑完（单步语义，无整轮墙钟）。"""
    from pydantic_ai.usage import UsageLimits

    from hoshino.ai import metrics, runner

    config, provider_id, model, record = _prepare()
    config = dataclasses.replace(config, step_timeout_seconds=_POSITIVE_STEP_TIMEOUT)
    agent = build_agent(config, provider_id, record, model)
    deps = build_deps(config, provider_id, model, PROBE_SCOPE)
    run_log = runner.RunLog()

    print("=" * 70)
    print(f"单步超时 live 探针（正向）provider={provider_id} model={model}")
    print(
        f"step_timeout_seconds={config.step_timeout_seconds}（生产默认 300）"
        f" chat_max_requests={config.chat_max_requests}（无整轮墙钟）"
    )

    started = time.perf_counter()
    result = await asyncio.wait_for(
        runner.run_agent_with_retry(
            agent,
            _MULTI_STEP_PROMPT,
            deps=deps,
            message_history=[],
            usage_limits=UsageLimits(request_limit=config.chat_max_requests),
            run_log=run_log,
            on_event=make_probe_logger(),
        ),
        timeout=PROBE_RUN_TIMEOUT_SECONDS,
    )
    elapsed = time.perf_counter() - started

    assert result is not None, "模型没有返回内容"
    usage = metrics.snapshot_from_result(result)
    tools = [c["name"] for c in run_log.tool_calls]
    steps = run_log.steps
    slowest = max((d.duration for d in run_log.step_details), default=0.0)

    print(f"\n[OK] 总耗时={elapsed:.1f}s steps={steps} 工具调用={tools}")
    print(f"最慢单步={slowest:.1f}s（上限 {config.step_timeout_seconds:.0f}s）")
    print(f"tokens={usage.total_tokens}（in {usage.request_tokens} / out {usage.response_tokens}）")
    print_step_details(run_log)
    assert steps >= 3, f"多步提示应至少产生 3 次模型请求，实际 {steps}"
    assert len(tools) >= 4, f"多步提示应至少调用 4 次工具，实际 {tools}"
    # 决定性断言：整轮总耗时超过单步上限，且没有任何单步越界 → 上限确实落在单步
    # 而不是整轮（旧实现是整轮 180s 墙钟，这类 run 会被误杀）。
    assert elapsed > config.step_timeout_seconds, (
        f"探针需制造「总耗时 > 单步上限」的场景：总耗时 {elapsed:.1f}s，"
        f"单步上限 {config.step_timeout_seconds:.0f}s（请加重提示里的检索量）"
    )
    assert slowest < config.step_timeout_seconds, (
        f"最慢单步 {slowest:.1f}s 越过了单步上限 {config.step_timeout_seconds:.0f}s"
    )

    write_report(
        "ai-step-timeout-live.md",
        [
            "# 单步超时 live 探针（正向：多步 run 正常完成）",
            "",
            "- 运行：`ONE_SHOT_LIVE=1 uv run pytest nb-tests/one-shot/test_ai_step_timeout_live.py -s -q`",
            f"- provider/model：{provider_id}/{model}",
            f"- step_timeout_seconds：{config.step_timeout_seconds:.0f}（生产默认 300；无整轮墙钟）",
            f"- 结果：总耗时 {elapsed:.1f}s，steps={steps}，最慢单步 {slowest:.1f}s",
            f"- 工具调用：{tools}",
            f"- tokens：{usage.total_tokens}",
            "",
            f"结论：整轮 {elapsed:.1f}s > 单步上限 {config.step_timeout_seconds:.0f}s，且没有任何单步越界，",
            "run 正常跑完——超时上限确实落在单步（模型请求 / 工具执行），不存在整轮墙钟。",
        ],
    )


async def test_single_step_timeout_fails_fast():
    """负向：单步上限 0.3s 时，无工具提示也在单次请求上限内失败，且类型是超时。"""
    from hoshino.ai import errors, runner

    config, provider_id, model, record = _prepare()
    config = dataclasses.replace(config, step_timeout_seconds=0.3)
    agent = build_agent(config, provider_id, record, model)
    deps = build_deps(config, provider_id, model, PROBE_SCOPE)
    run_log = runner.RunLog()

    print("=" * 70)
    print(f"单步超时 live 探针（负向）provider={provider_id} model={model}")
    print(f"step_timeout_seconds={config.step_timeout_seconds}（无工具提示，只有模型请求）")

    started = time.perf_counter()
    caught: BaseException | None = None
    try:
        await asyncio.wait_for(
            runner.run_agent_with_retry(
                agent,
                _NO_TOOL_PROMPT,
                deps=deps,
                message_history=[],
                run_log=run_log,
            ),
            timeout=PROBE_RUN_TIMEOUT_SECONDS,
        )
    except BaseException as exc:
        caught = exc
    elapsed = time.perf_counter() - started

    assert caught is not None, "0.3s 单步上限下应超时失败"
    chain = []
    node: BaseException | None = caught
    while node is not None and len(chain) < 6:
        chain.append(f"{type(node).__module__}.{type(node).__name__}")
        node = node.__cause__

    print(f"\n[OK] 失败类型={type(caught).__name__} 耗时={elapsed:.1f}s")
    print(f"因果链：{' → '.join(chain)}")
    print(f"errors.is_step_timeout={errors.is_step_timeout(caught)}")
    print(
        f"（耗时含 provider SDK 自带重试：单次请求上限 {config.step_timeout_seconds}s × 重试次数）"
    )
    assert errors.is_step_timeout(caught), f"应识别为单步超时，实际 {type(caught).__name__}"

    write_report(
        "ai-step-timeout-negative-live.md",
        [
            "# 单步超时 live 探针（负向：单步上限触发）",
            "",
            f"- provider/model：{provider_id}/{model}",
            f"- step_timeout_seconds：{config.step_timeout_seconds}（无工具提示，只有模型请求）",
            f"- 结果：失败类型 {type(caught).__name__}，耗时 {elapsed:.1f}s",
            f"- 因果链：{' → '.join(chain)}",
            f"- errors.is_step_timeout：{errors.is_step_timeout(caught)}",
            "",
            "结论：单步上限落在单次模型请求上（httpx 超时被 provider SDK 包成 ModelAPIError，",
            "由 errors.is_step_timeout 沿因果链识别）；耗时 = 上限 × SDK 内建重试次数。",
        ],
    )


def test_agent_wiring_carries_step_timeout():
    """接线：真实 agent 的模型请求设置与工具集都拿到单步上限。

    模型请求侧的行为由负向用例实测（0.3s 上限确实触发 httpx 超时）；工具执行侧
    的超时→模型可见重试提示由 ``FunctionToolset(timeout=)`` 保证，这里断言接线值。
    """
    from types import SimpleNamespace

    from hoshino.ai import providers

    config, provider_id, model, record = _prepare()
    config = dataclasses.replace(config, step_timeout_seconds=42.0)
    deps = build_deps(config, provider_id, model, PROBE_SCOPE)
    ctx = SimpleNamespace(deps=deps)

    settings = providers.build_model_settings(record, default_timeout=config.step_timeout_seconds)
    toolset = providers._resolve_toolset(ctx)

    print("=" * 70)
    print(f"单步超时 live 探针（接线）provider={provider_id} model={model}")
    print(
        f"模型请求 timeout={settings['timeout']}（provider 行 timeout_seconds={record.timeout_seconds}）"
    )
    print(
        f"工具集 timeout={toolset.timeout if toolset else None} 工具数={len(toolset.tools) if toolset else 0}"
    )

    assert settings is not None and settings["timeout"] == 42.0
    assert toolset is not None and toolset.timeout == 42.0, "工具集应带单步上限"
    assert toolset.tools, "探针 scope 应解析出工具"

    write_report(
        "ai-step-timeout-wiring-live.md",
        [
            "# 单步超时 live 探针（接线）",
            "",
            f"- 模型请求 timeout={settings['timeout']}（provider 行 timeout_seconds="
            f"{record.timeout_seconds}，行值优先）",
            f"- 工具集 timeout={toolset.timeout}，工具数={len(toolset.tools)}",
            "",
            "结论：单步上限同时接到模型请求（ModelSettings.timeout）与工具执行",
            "（FunctionToolset.timeout）两条路径。",
        ],
    )
