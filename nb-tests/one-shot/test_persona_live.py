"""真实 provider 人格 live 测试：评估默认人格在四领域的表现。

运行：

    ONE_SHOT_LIVE=1 uv run pytest nb-tests/one-shot/test_persona_live.py -s -q
    # 只跑部分领域：ONE_SHOT_LIVE=1 ONE_SHOT_DOMAINS="学术 人文历史" uv run pytest ...

与 ``hoshino/modules/ai/chat.py`` 的完整链路同构（provider/模型解析、
build_agent、run_agent_with_retry、护栏），对 fixtures/persona.json 里
生活 / 学术 / 技术实践 / 人文历史 四领域的问题各发起单轮对话（每问独立空
上下文）。不注入真实事件（bot=None, event=None）。结果打印到 stdout 并落
agent-plan-report/ai-persona-live-probe.md；probe scope 的 memory 与模型误调
persona_manage 新建的 persona 在结束后清理/恢复。
"""

from __future__ import annotations

import asyncio
import os
import time
from types import SimpleNamespace
from typing import Any

import pytest
from _live import build_agent, build_deps, load_config, load_fixture, write_report

pytestmark = [
    pytest.mark.skipif(
        not os.environ.get("ONE_SHOT_LIVE"),
        reason="联网探针：设置 ONE_SHOT_LIVE=1 才运行",
    ),
]

PROBE_SCOPE = "probe:persona-live"
_FIXTURE = load_fixture("persona")


def _want_domains() -> set[str] | None:
    """ONE_SHOT_DOMAINS="学术 人文历史" → 只跑这些领域（缺省全部）。"""
    raw = os.environ.get("ONE_SHOT_DOMAINS", "").strip()
    if not raw:
        return None
    return {part for part in raw.replace(",", " ").split() if part}


async def _ask(agent: Any, deps: Any, question: str, config: Any) -> dict[str, Any]:
    """单轮对话：与 chat.py 相同的 run 路径与护栏。"""
    from pydantic_ai.usage import UsageLimits

    from hoshino.ai import metrics, reply, runner

    run_log = runner.RunLog()
    started = time.perf_counter()
    try:
        result = await asyncio.wait_for(
            runner.run_agent_with_retry(
                agent,
                question,
                deps=deps,
                message_history=[],
                usage_limits=UsageLimits(request_limit=config.chat_max_requests),
                run_log=run_log,
            ),
            timeout=config.chat_run_timeout_seconds,
        )
    except Exception as exc:
        elapsed = time.perf_counter() - started
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}", "elapsed": elapsed}

    usage = metrics.snapshot_from_result(result)
    # 输出可能是 reply 工具交回的 Reply（形态 + 正文），归一后再记录。
    delivered = reply.to_delivery(result.output)
    return {
        "ok": True,
        "text": delivered.content,
        "format": delivered.format,
        "elapsed": time.perf_counter() - started,
        "steps": run_log.steps,
        "usage": usage,
        "tools": list(run_log.tool_calls),
    }


def _cleanup_memory() -> None:
    """清理 probe scope 的 memory（若模型误调 memory 工具）。"""
    from hoshino.ai import store

    for key in store.memory_list_keys(PROBE_SCOPE):
        store.memory_delete(PROBE_SCOPE, key)


async def test_persona_domains():
    """每个领域问题各跑一轮真实对话，断言全部成功并打印表现。"""
    from hoshino.ai import provider, providers

    wanted = _want_domains()
    questions = [q for q in _FIXTURE["questions"] if not wanted or q["domain"] in wanted]
    assert questions, f"领域过滤后没有问题：wanted={wanted}"

    config = load_config()
    provider_id, model = provider.resolve_model(PROBE_SCOPE)
    assert provider_id and model, "未配置默认文本模型（请先 `ai model default`）"
    record = provider.get_provider(provider_id)
    assert record is not None, f"provider `{provider_id}` 不存在于 aichat.db"

    deps = build_deps(config, provider_id, model, PROBE_SCOPE)
    agent = build_agent(config, provider_id, record, model)
    ctx = SimpleNamespace(deps=SimpleNamespace(task=None, scope_key=PROBE_SCOPE, config=config))
    system_prompt = await providers._persona_system_prompt(ctx)
    print(f"provider={provider_id} model={model}")
    print(f"system prompt（persona + 示例对话 + 输出规范）：{len(system_prompt)} 字")

    results: list[dict[str, Any]] = []
    try:
        for q in questions:
            print(f"\n{'=' * 70}\n[{q['domain']}] {q['question']}", flush=True)
            res = await _ask(agent, deps, q["question"], config)
            res["domain"] = q["domain"]
            res["question"] = q["question"]
            results.append(res)
            if res["ok"]:
                print(
                    f"✅ 形态={res['format']} [{res['elapsed']:.1f}s] steps={res['steps']} "
                    f"tokens={res['usage'].total_tokens}（in {res['usage'].request_tokens}"
                    f" / out {res['usage'].response_tokens}）"
                )
                print(res["text"])
            else:
                print(f"❌ [{res['elapsed']:.1f}s] {res['error']}")
    finally:
        _cleanup_memory()

    failed = [r for r in results if not r["ok"]]
    detail = "；".join(f"[{r['domain']}] {r['error']}" for r in failed)
    assert not failed, f"{len(failed)}/{len(results)} 个问题失败：{detail}"

    lines = ["# AI 人格 live 探针报告", "", f"- 时间：{time.strftime('%Y-%m-%d %H:%M')}", ""]
    for r in results:
        lines += [
            f"## [{r['domain']}] {r['question']}",
            "",
            (
                f"- 形态 {r.get('format', '-')} / 耗时 {r['elapsed']:.1f}s / "
                f"steps {r['steps']} / "
                f"tokens {r['usage'].total_tokens}（in {r['usage'].request_tokens} "
                f"/ out {r['usage'].response_tokens}）/ "
                f"工具 {[t['name'] for t in r['tools']] or '无'}"
            ),
            "",
            "```text",
            r.get("text", "") if r["ok"] else "（请求失败，无回复）",
            "```",
            "",
        ]
    suffix = "-filtered" if wanted else ""
    write_report(f"ai-persona-live-probe{suffix}.md", lines)
