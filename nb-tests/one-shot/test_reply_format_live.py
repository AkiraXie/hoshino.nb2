"""真实 provider 形态选择 live 探针：模型是否按「会话类型」选对交付形态。

运行：

    ONE_SHOT_LIVE=1 uv run pytest nb-tests/one-shot/test_reply_format_live.py -s -q

与 ``hoshino/modules/ai/chat.py`` 同构（provider/模型解析、build_agent、
run_agent_with_retry、护栏），对闲聊 / 事实搜索 / 待复制内容 / 对比分析 /
知识讲解各发起一轮真实对话，检查：

- 闲聊、事实、待复制内容 → 走纯文本（``format=text``，或直接写不带 Markdown 的文字）；
- 对比、知识整理 → 走图片（``format=image``，或写了 Markdown 被自动判定为图片）。

只读配置与 provider 行，不落库；结果打印到 stdout 并落
agent-plan-report/ai-reply-format-live-probe.md。
"""

from __future__ import annotations

import asyncio
import os
import time
from typing import Any

import pytest
from _live import build_agent, build_deps, load_config, write_report

pytestmark = [
    pytest.mark.skipif(
        not os.environ.get("ONE_SHOT_LIVE"),
        reason="联网探针：设置 ONE_SHOT_LIVE=1 才运行",
    ),
]

PROBE_SCOPE = "probe:reply-format-live"

# (场景, 提问, 期望形态)
CASES: list[tuple[str, str, str]] = [
    ("闲聊", "早啊，今天也要加油哦", "text"),
    ("事实", "现在北京时间几点？顺便说下今天星期几", "text"),
    ("待复制", "给我三条最常用的 git 命令，我要直接复制到终端里用", "text"),
    ("翻译复述", "把这句话原样翻成英文：这个功能下周上线，记得提前通知测试。", "text"),
    ("对比分析", "对比一下 Redis 和 Memcached，从数据结构、持久化、适用场景几个方面说", "image"),
    ("知识讲解", "讲讲 TCP 三次握手到底在解决什么问题，为什么两次不行", "image"),
]


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
        return {
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}",
            "elapsed": time.perf_counter() - started,
        }

    delivered = reply.to_delivery(result.output)
    usage = metrics.snapshot_from_result(result)
    return {
        "ok": True,
        "chosen": isinstance(result.output, reply.Reply),
        "format": delivered.format,
        "content": delivered.content,
        "elapsed": time.perf_counter() - started,
        "steps": run_log.steps,
        "usage": usage,
        "tools": [c["name"] for c in run_log.tool_calls],
    }


async def test_reply_format_selection():
    """逐场景跑真实对话，检查形态是否与预期一致。"""
    from hoshino.ai import provider

    config = load_config()
    provider_id, model = provider.resolve_model(PROBE_SCOPE)
    assert provider_id and model, "未配置默认文本模型（请先 `ai model default`）"
    record = provider.get_provider(provider_id)
    assert record is not None, f"provider `{provider_id}` 不存在于 aichat.db"

    deps = build_deps(config, provider_id, model, PROBE_SCOPE)
    agent = build_agent(config, provider_id, record, model)
    print(f"provider={provider_id} model={model}")

    results: list[dict[str, Any]] = []
    for scene, question, want in CASES:
        print(f"\n{'=' * 70}\n[{scene}] {question}", flush=True)
        res = await _ask(agent, deps, question, config)
        res.update({"scene": scene, "question": question, "want": want})
        results.append(res)
        if not res["ok"]:
            print(f"❌ [{res['elapsed']:.1f}s] {res['error']}")
            continue
        hit = "✅" if res["format"] == want else "⚠️"
        print(
            f"{hit} 形态={res['format']}（期望 {want}）· "
            f"{'工具选择' if res['chosen'] else '自动判定'} · "
            f"[{res['elapsed']:.1f}s] steps={res['steps']} "
            f"工具={res['tools'] or '无'} tokens={res['usage'].total_tokens}"
        )
        print(res["content"][:600])

    failed = [r for r in results if not r["ok"]]
    assert not failed, "；".join(f"[{r['scene']}] {r['error']}" for r in failed)

    lines = ["# AI 回复形态 live 探针报告", "", f"- 时间：{time.strftime('%Y-%m-%d %H:%M')}", ""]
    for r in results:
        lines += [
            f"## [{r['scene']}] 期望 {r['want']} → 实际 {r['format']}"
            f"（{'工具选择' if r['chosen'] else '自动判定'}）",
            "",
            f"提问：{r['question']}",
            "",
            (
                f"- 耗时 {r['elapsed']:.1f}s / steps {r['steps']} / "
                f"tokens {r['usage'].total_tokens} / 工具 {r['tools'] or '无'}"
            ),
            "",
            "```text",
            r["content"][:2000],
            "```",
            "",
        ]
    write_report("ai-reply-format-live-probe.md", lines)
