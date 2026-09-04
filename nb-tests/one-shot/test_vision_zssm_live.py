"""zssm 原生多模态 live 测试：真实 provider + 本地图片，验证「看图 → 结构化解释」。

运行：

    ONE_SHOT_LIVE=1 uv run pytest nb-tests/one-shot/test_vision_zssm_live.py -s -q

与 ``hoshino/modules/ai/zssm`` 的完整链条同构：消息 ``zssm [图片]``（无文本，
仅图片；图片路径在 fixtures/vision_zssm.json），同一 model 一次吃 JSON 文本 +
压缩 BinaryContent。验证 ZssmOutput 结构化字段；耗时 / 每步 duration / token
用量打印到 stdout（``-s`` 可见），报告落 agent-plan-report/。
设 ``AI_LOG_REQUEST_PAYLOAD=1`` 可在 DEBUG 日志看到发往 provider 的请求体。
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from types import SimpleNamespace
from typing import Any

import pytest
from _live import (
    build_deps,
    load_config,
    load_fixture,
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

PROBE_SCOPE = "probe:vision-zssm-live"
_FIXTURE = load_fixture("vision_zssm")


def _image_bytes(image_parts: list[Any]) -> int:
    return sum(len(getattr(c, "data", b"")) for c in image_parts)


async def test_vision_zssm_native_multimodal():
    """纯图输入走原生多模态，产出合法 ZssmOutput（结构化字段校验）。"""
    from pydantic_ai.messages import TextContent
    from pydantic_ai.usage import UsageLimits

    from hoshino.ai import media, metrics, provider, runner, store
    from hoshino.modules.ai.zssm import (
        _MAX_REQUESTS,
        _TIMEOUT_SECONDS,
        ZssmOutput,
        _build_zssm_agent,
        _format_keywords,
        _zssm_system_prompt,
    )

    store.ensure_schema()
    config = load_config()
    model_pid, model_name = provider.resolve_model(PROBE_SCOPE)
    record = provider.get_provider(model_pid) if model_pid else None
    assert record is not None and model_name, (
        "未配置默认模型（超级用户 `ai model default <provider> <模型>`）"
    )

    image_path = resolve_image(_FIXTURE["image"])
    image_parts = media.image_segments_to_content(
        [SimpleNamespace(path=str(image_path), raw=None, url="")]
    )
    assert image_parts, f"图片解析失败：{image_path}"
    payload = {"target": "", "focus": ""}
    text_part = TextContent(content=json.dumps(payload, ensure_ascii=False))
    prompt = [text_part, *image_parts]
    system_prompt = _zssm_system_prompt()
    agent = _build_zssm_agent(
        record, model_name, proxy=provider.resolve_effective_proxy(record, config.proxy)
    )

    print("=" * 70)
    print(f"图片：{image_path.absolute()}（{image_path.stat().st_size:,}B）")
    print(f"model：{model_pid}/{model_name}；payload：{text_part.content}")
    print(
        f"prompt parts：TextContent({len(text_part.content)}字) + BinaryContent({_image_bytes(image_parts):,}B)"
    )
    print(f"system prompt（zssm 人设 + 时间戳）：{len(system_prompt)} 字")

    run_log = runner.RunLog()
    started = time.perf_counter()
    result = await asyncio.wait_for(
        runner.run_agent(
            agent,
            prompt,
            deps=build_deps(config, model_pid, model_name, PROBE_SCOPE),
            usage_limits=UsageLimits(request_limit=_MAX_REQUESTS),
            run_log=run_log,
        ),
        timeout=_TIMEOUT_SECONDS,
    )
    elapsed = time.perf_counter() - started

    assert result is not None, "模型没有返回内容"
    usage = metrics.snapshot_from_result(result)
    out: ZssmOutput = result.output
    assert isinstance(out, ZssmOutput), f"output 类型 {type(out).__name__} != ZssmOutput"
    if out.blocked:
        print(f"\n⚠️ 模型 blocked=True（不判失败）：{out.output[:80]}")
    else:
        assert out.keywords, "blocked=False 但 keywords 为空"
        assert out.output.strip(), "blocked=False 但 output 为空"

    print(
        f"\n[OK] 耗时={elapsed:.1f}s（run_log {run_log.ended_at - run_log.started_at:.1f}s）"
        f" steps={run_log.steps} tokens in {usage.request_tokens} / out {usage.response_tokens}"
    )
    print(f"工具调用：{[t['name'] for t in run_log.tool_calls] or '无'}")
    print_step_details(run_log)
    print(f"\nkeywords：{_format_keywords(out.keywords)}")
    print(f"\n{out.output}")

    write_report(
        "ai-vision-zssm-live-probe.md",
        [
            "# zssm 原生多模态 live 探针报告",
            "",
            f"- 时间：{time.strftime('%Y-%m-%d %H:%M')}",
            f"- 图片：`{image_path.name}`（{image_path.stat().st_size:,}B）；model：`{model_pid}/{model_name}`",
            f"- 整次 run：{elapsed:.1f}s / {run_log.steps} steps",
            f"- token：in {usage.request_tokens} / out {usage.response_tokens} / "
            f"缓存读 {usage.cache_read_tokens}",
            f"- 工具调用：{[t['name'] for t in run_log.tool_calls] or '无'}",
            "",
            f"- blocked：{out.blocked}",
            f"- keywords：{out.keywords}",
            "",
            out.output,
            "",
            "注：本文不含任何 key/token，密钥仅存在于 aichat.db",
        ],
    )
