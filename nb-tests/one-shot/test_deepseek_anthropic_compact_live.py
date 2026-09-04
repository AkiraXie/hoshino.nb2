"""DeepSeek Anthropic 端点的远程压缩（compact）支持 live 测试。

运行：

    ONE_SHOT_LIVE=1 uv run pytest nb-tests/one-shot/test_deepseek_anthropic_compact_live.py -s -q

只读 aichat.db 的 deepseek provider key（内存使用，不落盘、不打印），用
anthropic kind 指向 https://api.deepseek.com/anthropic 实测：

1. baseline：普通对话请求能通（断言）；
2. 远程压缩：在请求里附加 ``CompactionPart``，观察 DeepSeek 的 anthropic 兼容
   端点是否接受（记录性质：被拒绝/报错只打印，不判失败——这是上游能力探测）。

参数在 fixtures/deepseek_anthropic_compact.json。
"""

from __future__ import annotations

import os

import pytest
from _live import load_fixture

pytestmark = [
    pytest.mark.skipif(
        not os.environ.get("ONE_SHOT_LIVE"),
        reason="联网探针：设置 ONE_SHOT_LIVE=1 才运行",
    ),
]

_FIXTURE = load_fixture("deepseek_anthropic_compact")


def _load_deepseek_key() -> str | None:
    """只读 provider key（不打印）。"""
    from hoshino.ai import store

    for row in store.list_provider_rows():
        if row["id"].lower() == "deepseek" and row.get("key"):
            return row["key"]
    return None


async def test_anthropic_endpoint_and_compaction():
    """baseline 请求必须通；CompactionPart 请求的结果仅记录不判失败。"""
    import httpx
    from pydantic_ai.models import ModelRequestParameters, ModelSettings
    from pydantic_ai.models.anthropic import AnthropicModel
    from pydantic_ai.providers.anthropic import AnthropicProvider

    key = _load_deepseek_key()
    if not key:
        pytest.skip("deepseek provider 未配置或缺少 key")
    base = _FIXTURE["base_url"]
    model_name = _FIXTURE["model"]

    from pydantic_ai.messages import CompactionPart, ModelRequest, ModelResponse, UserPromptPart

    # 1. baseline：普通请求
    client = httpx.AsyncClient(timeout=httpx.Timeout(60.0), trust_env=False)
    model = AnthropicModel(
        model_name,
        provider=AnthropicProvider(api_key=key, base_url=base, http_client=client),
    )
    base_history = [ModelRequest(parts=[UserPromptPart(content=_FIXTURE["baseline_prompt"])])]
    try:
        response = await model.request(base_history, ModelSettings(), ModelRequestParameters())
        print(f"baseline request OK：{type(response).__name__} text={response.text[:50]}")
        assert response is not None
    finally:
        await client.aclose()

    # 2. 远程压缩：模拟「旧历史已压缩」，后续请求带 CompactionPart
    client = httpx.AsyncClient(timeout=httpx.Timeout(60.0), trust_env=False)
    model = AnthropicModel(
        model_name,
        provider=AnthropicProvider(api_key=key, base_url=base, http_client=client),
    )
    compact_history = [
        ModelResponse(parts=[CompactionPart(content=_FIXTURE["compact_summary"])]),
        ModelRequest(parts=[UserPromptPart(content=_FIXTURE["compact_prompt"])]),
    ]
    try:
        response = await model.request(compact_history, ModelSettings(), ModelRequestParameters())
        print(f"compaction-part request OK：text={response.text[:80]}")
        print("DeepSeek anthropic 端点接受 CompactionPart")
    except Exception as exc:
        print(f"compaction-part 请求失败（记录，不判失败）：{type(exc).__name__}: {exc}")
        body = getattr(exc, "body", None)
        if body:
            print("body:", str(body)[:600])
    finally:
        await client.aclose()
