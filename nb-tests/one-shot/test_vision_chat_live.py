"""AI 原生多模态聊天 live 测试：真实 provider + 本地图片，验证「看图作答」链路。

运行：

    ONE_SHOT_LIVE=1 uv run pytest nb-tests/one-shot/test_vision_chat_live.py -s -q

与 ``hoshino/modules/ai/chat.py`` 的完整链路同构：``#<消息>[图片]``（消息与图片
在 fixtures/vision_chat.json），统一 model 槽同时吃文本与图片（原生多模态，
非 vision→text 两段式）。耗时 / 每步 duration / token 用量打印到 stdout，
报告落 agent-plan-report/。设 ``AI_LOG_REQUEST_PAYLOAD=1`` 可在 DEBUG 日志看到
发往 provider 的请求体。
"""

from __future__ import annotations

import asyncio
import os
import time
from types import SimpleNamespace
from typing import Any

import pytest
from _live import (
    build_agent,
    build_deps,
    load_config,
    load_fixture,
    make_probe_logger,
    print_step_details,
    resolve_image,
    write_report,
)

pytestmark = [
    pytest.mark.skipif(
        not os.environ.get("ONE_SHOT_LIVE"),
        reason="联网探针：设置 ONE_SHOT_LIVE=1 才运行",
    ),
]

PROBE_SCOPE = "probe:vision-chat-live"
_FIXTURE = load_fixture("vision_chat")


def _image_bytes(image_parts: list[Any]) -> int:
    return sum(len(getattr(c, "data", b"")) for c in image_parts)


async def test_vision_chat_native_multimodal():
    """同一 model 一次吃文本 + 图片作答（原生多模态链路）。"""
    from pydantic_ai.usage import UsageLimits

    from hoshino.ai import media, metrics, provider, providers, rendering, runner, store

    store.ensure_schema()
    config = load_config()
    model_pid, model_name = provider.resolve_model(PROBE_SCOPE)
    record = provider.get_provider(model_pid) if model_pid else None
    assert record is not None and model_name, (
        "未配置默认模型（超级用户 `ai model default <provider> <模型>`）"
    )

    image_path = resolve_image(_FIXTURE["image"])
    message = _FIXTURE["message"]
    image_parts = media.image_segments_to_content(
        [SimpleNamespace(path=str(image_path), raw=None, url="")]
    )
    assert image_parts, f"图片解析失败：{image_path}"
    prompt = media.build_image_prompt(message, image_parts)
    deps = build_deps(config, model_pid, model_name, PROBE_SCOPE)
    agent = build_agent(config, model_pid, record, model_name)
    ctx = SimpleNamespace(deps=SimpleNamespace(task=None, scope_key=PROBE_SCOPE, config=config))
    system_prompt = await providers._persona_system_prompt(ctx)

    print("=" * 70)
    print("AI 原生多模态聊天 live 探针")
    print(f"图片：{image_path.absolute()}（{image_path.stat().st_size:,}B）")
    print(f"消息：`#{message}[图片]`（text 部分去掉 # 前缀 → `{message}`）")
    print(f"model：{model_pid}/{model_name}；图片载荷：{_image_bytes(image_parts):,}B")
    print(f"system prompt（persona + 输出规范 + 时间戳）：{len(system_prompt)} 字")

    run_log = runner.RunLog()
    started = time.perf_counter()
    result = await asyncio.wait_for(
        runner.run_agent_with_retry(
            agent,
            prompt,
            deps=deps,
            message_history=[],
            usage_limits=UsageLimits(request_limit=config.chat_max_requests),
            run_log=run_log,
            on_event=make_probe_logger(),
        ),
        timeout=config.chat_run_timeout_seconds,
    )
    elapsed = time.perf_counter() - started

    assert result is not None, "模型没有返回内容"
    usage = metrics.snapshot_from_result(result)
    hit = metrics.cache_hit_ratio(usage.request_tokens, usage.cache_read_tokens)
    raw = rendering.strip_trailing_summary(result.output)
    assert raw.strip(), "回复为空"

    print(
        f"\n[OK] 耗时={elapsed:.1f}s steps={run_log.steps} tokens={usage.total_tokens}"
        f"（in {usage.request_tokens} / out {usage.response_tokens} / 命中率 {hit:.1%}）"
    )
    print(f"工具调用：{[t['name'] for t in run_log.tool_calls] or '无'}")
    print_step_details(run_log)
    print("\n回复：")
    print(raw)

    write_report(
        "ai-vision-chat-live-probe.md",
        [
            "# AI 原生多模态聊天 live 探针报告",
            "",
            f"- 时间：{time.strftime('%Y-%m-%d %H:%M')}",
            f"- 图片：`{image_path.name}`（{image_path.stat().st_size:,}B）；"
            f"model：`{model_pid}/{model_name}`",
            f"- 消息：`#{message}[图片]`；会话：空上下文",
            f"- 整次 run：{elapsed:.1f}s / {run_log.steps} steps",
            f"- token：in {usage.request_tokens} / out {usage.response_tokens} / 命中率 {hit:.1%}",
            "",
            "## 最终回复",
            "",
            raw,
            "",
            "注：本文不含任何 key/token，密钥仅存在于 aichat.db",
        ],
    )
