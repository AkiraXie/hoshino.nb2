"""真实 provider 人格探针（手动运行，非 pytest 用例）。

按 ``hoshino/modules/ai/chat.py`` 的完整链路，用仓库真实配置（service_config/
aichat.json + data/db/aichat.db 的 provider 行）向真实模型发起单轮对话，
覆盖 生活 / 学术 / 技术实践 / 人文历史 四个领域，用于评估默认人格的表现
（是否死板、是否贴合元气少女人设、输出规范是否生效）。

运行：
    uv run python nb-tests/one-shot/live_ai_persona_probe.py

行为说明：
- 与 chat.py 相同的 provider/模型解析、build_agent、run_agent_with_retry、护栏；
- 每问独立空上下文（隔离各领域表现，不串历史）；
- 不注入真实事件（bot=None, event=None）：send_message / service_manage 不注入，
  computer 高风险的 bash/python 不注入（与 chat 一致）；
- 副作用清理：probe scope 的 memory 写入与模型误调 persona_manage 新建的
  persona 会在结束后恢复/删除；不写 usage 事件。
- 结果输出到 stdout，同时落 agent-plan-report/ai-persona-live-probe.md。
"""

from __future__ import annotations

import asyncio
import sys
import time
from types import SimpleNamespace
from typing import Any

from nonebot_plugin_alconna.uniseg import Target
from pydantic_ai.usage import UsageLimits

from hoshino.ai import metrics, provider, providers, rendering, runner, store
from hoshino.ai.config import AIConfig
from hoshino.ai.deps import AgentDeps, PermissionSnapshot, Telemetry

PROBE_SCOPE = "probe:persona-live"

QUESTIONS: list[dict[str, str]] = [
    {
        "domain": "生活",
        "question": "今天加班到九点，累死了，回家只想瘫着，有什么不用开火就能搞定的晚饭推荐吗？",
    },
    {
        "domain": "生活",
        "question": "周末想约朋友去公园野餐，帮我列个物品清单呗，还要注意啥？",
    },
    {
        "domain": "学术",
        "question": "帮我解释下薛定谔的猫到底想说啥？跟哥本哈根诠释有什么关系？说人话就行",
    },
    {
        "domain": "学术",
        "question": "写毕业论文开题报告，文献综述部分总是写不好，有什么思路吗？",
    },
    {
        "domain": "技术实践",
        "question": "我 Python 脚本老报 IndexError: list index out of range，怎么快速定位是哪一行的问题？",
    },
    {
        "domain": "技术实践",
        "question": "Docker 容器里跑 cron 任务，日志时间差 8 小时，时区不对，怎么改？",
    },
    {
        "domain": "人文历史",
        "question": "为什么都说唐朝万国来朝？唐朝真的那么开放吗？跟明清比有啥不一样？",
    },
    {
        "domain": "人文历史",
        "question": "网上说崇祯是被李自成逼死的，也有人说他其实可以跑到南京，你怎么看明朝灭亡这件事？",
    },
]


def load_config() -> AIConfig:
    """从 HoshinoConfig 读取 AI 配置（挂载字段 AI_*，读自 .env.prod）。"""
    from hoshino.ai.base import get_config

    return get_config()


def build_deps(config: AIConfig, provider_id: str, model: str) -> AgentDeps:
    """与 construct_chat_deps 同构，但 bot/event 为 None（无真实事件）。"""
    return AgentDeps(
        surface="chat",
        scope_key=PROBE_SCOPE,
        target=Target(id="0", private=True, self_id="10000", adapter="milky"),
        config=config,
        permissions=PermissionSnapshot(),
        bot=None,
        event=None,
        telemetry=Telemetry(provider_id=provider_id, scope_key=PROBE_SCOPE, model=model),
    )


async def effective_system_prompt(config: AIConfig) -> str:
    """取模型实际看到的 system prompt（persona + 示例对话 + 输出规范）。"""
    ctx = SimpleNamespace(deps=SimpleNamespace(task=None, scope_key=PROBE_SCOPE, config=config))
    return await providers._persona_system_prompt(ctx)


async def ask(agent, deps: AgentDeps, question: str, config: AIConfig) -> dict[str, Any]:
    """单轮对话：与 chat.py 相同的 run 路径与护栏。"""
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
            "tools": run_log.tool_calls,
            "steps": run_log.steps,
        }
    elapsed = time.perf_counter() - started
    usage = metrics.snapshot_from_result(result)
    return {
        "ok": True,
        "text": rendering.strip_trailing_summary(result.output),
        "elapsed": elapsed,
        "usage": usage,
        "tools": run_log.tool_calls,
        "steps": run_log.steps,
    }


def cleanup_probe_side_effects(before_personas: list[str]) -> None:
    """清理探针副作用：probe scope 的 memory、误建的新 persona。"""
    for key in store.memory_list_keys(PROBE_SCOPE):
        store.memory_delete(PROBE_SCOPE, key)
    after = {p["name"] for p in store.list_personas()}
    for name in after - set(before_personas):
        store.delete_persona(name)


def main() -> None:
    only = set(sys.argv[1:])  # 可选：按领域过滤，如 `python ... 学术 人文历史`
    config = load_config()
    provider_id = config.default
    record = provider.get_provider(provider_id)
    if record is None:
        raise SystemExit(f"provider `{provider_id}` 不存在于 aichat.db")
    model = provider.resolve_text_model(PROBE_SCOPE, provider_id)
    if not model:
        raise SystemExit(f"provider `{provider_id}` 未配置文本模型")

    before_personas = [p["name"] for p in store.list_personas()]
    deps = build_deps(config, provider_id, model)
    agent = providers.build_agent(
        provider_id,
        record,
        model,
        proxy=provider.resolve_effective_proxy(record, config.proxy),
        web_search_native=config.web_search_native,
        tool_max_retries=config.tool_max_retries,
    )

    system_prompt = asyncio.run(effective_system_prompt(config))
    effective_proxy = provider.resolve_effective_proxy(record, config.proxy)
    print("=" * 70)
    print("真实 provider 人格探针")
    print(f"provider={provider_id} kind={record.kind} url={record.url}")
    print(f"model={model} proxy={effective_proxy or '直连'}")
    print("persona 解析: 默认级（无全局/scope 绑定）")
    print("-" * 70)
    print("system prompt 全文（模型实际看到）：")
    print(system_prompt)
    print("=" * 70)

    results: list[dict[str, Any]] = []
    for item in QUESTIONS:
        if only and item["domain"] not in only:
            continue
        q = item["question"]
        print(f"\n>>> [{item['domain']}] {q}")
        res = asyncio.run(ask(agent, deps, q, config))
        results.append({"domain": item["domain"], "question": q, **res})
        if res["ok"]:
            print(
                f"[{res['elapsed']:.1f}s steps={res['steps']} "
                f"tokens={res['usage'].total_tokens} tools="
                f"{[t['name'] for t in res['tools']] or '-'}]"
            )
            print(res["text"])
        else:
            print(f"[FAIL {res['elapsed']:.1f}s] {res['error']}")

    cleanup_probe_side_effects(before_personas)

    # ---- 落盘报告 ----
    lines = [
        "# AI 人格真实 provider 探针报告",
        "",
        f"- 时间：{time.strftime('%Y-%m-%d %H:%M')}",
        f"- provider：`{provider_id}`（kind={record.kind}，url={record.url}）",
        f"- 模型：`{model}`（proxy={effective_proxy or '直连'}）",
        "- 会话：每问独立空上下文；无全局/scope persona 绑定 → 默认人格",
        "- 注意：本文不含任何 key/token，密钥仅存在于 aichat.db",
        "",
        "## system prompt（模型实际看到）",
        "",
        "```text",
        system_prompt,
        "```",
        "",
    ]
    for idx, r in enumerate(results, 1):
        lines.append(f"## Q{idx} [{r['domain']}] {r['question']}")
        lines.append("")
        if r["ok"]:
            lines.append(
                f"- 耗时 {r['elapsed']:.1f}s / steps {r['steps']} / "
                f"tokens {r['usage'].total_tokens}（in {r['usage'].request_tokens} "
                f"/ out {r['usage'].response_tokens}）/ "
                f"工具 {[t['name'] for t in r['tools']] or '无'}"
            )
        else:
            lines.append(f"- FAIL：{r['error']}")
        lines.append("")
        lines.append("```text")
        lines.append(r.get("text", "") if r["ok"] else "(请求失败，无回复)")
        lines.append("```")
        lines.append("")
    import os

    os.makedirs("agent-plan-report", exist_ok=True)
    suffix = "-filtered" if only else ""
    path = f"agent-plan-report/ai-persona-live-probe{suffix}.md"
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    print(f"\n报告已写入 {path}")


if __name__ == "__main__":
    main()
