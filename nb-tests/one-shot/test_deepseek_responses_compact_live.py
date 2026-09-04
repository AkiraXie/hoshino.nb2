"""DeepSeek OpenAI Responses 端点的远程压缩（compact）支持 live 测试。

运行：

    ONE_SHOT_LIVE=1 uv run pytest nb-tests/one-shot/test_deepseek_responses_compact_live.py -s -q

只读 aichat.db 的 deepseek provider key（内存使用，不落盘、不打印），用
openai_responses kind 指向 https://api.deepseek.com 实测：

1. /responses 可用模型列表（GET /models，断言非空）；
2. ``responses.compact`` 远程压缩是否可用：构造假历史 →
   ``model.compact_messages(ctx)``（记录性质：被拒绝只打印，不判失败——
   这是上游能力探测）。

参数在 fixtures/deepseek_responses_compact.json。
"""

from __future__ import annotations

import os

import httpx
import pytest
from _live import load_fixture

pytestmark = [
    pytest.mark.skipif(
        not os.environ.get("ONE_SHOT_LIVE"),
        reason="联网探针：设置 ONE_SHOT_LIVE=1 才运行",
    ),
]

_FIXTURE = load_fixture("deepseek_responses_compact")


def _load_deepseek_key() -> str | None:
    """只读 provider key（不打印）。"""
    from hoshino.ai import store

    for row in store.list_provider_rows():
        if row["id"].lower() == "deepseek" and row.get("key"):
            return row["key"]
    return None


def _history_from_fixture() -> list:
    """fixtures 的 user/assistant 轮次 → pydantic-ai 消息历史。"""
    from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, UserPromptPart

    turns = []
    for turn in _FIXTURE["sample_turns"]:
        part_cls = UserPromptPart if turn["role"] == "user" else TextPart
        msg_cls = ModelRequest if turn["role"] == "user" else ModelResponse
        turns.append(msg_cls(parts=[part_cls(content=turn["text"])]))
    return turns


async def test_responses_endpoint_and_compact():
    """GET /models 拿模型列表（断言非空），再探测 compact_messages 可用性。"""
    from pydantic_ai.models import ModelRequestContext, ModelRequestParameters, ModelSettings
    from pydantic_ai.models.openai import OpenAIResponsesModel
    from pydantic_ai.providers.openai import OpenAIProvider

    key = _load_deepseek_key()
    if not key:
        pytest.skip("deepseek provider 未配置或缺少 key")
    base = _FIXTURE["base_url"]

    # 1. 可用模型
    async with httpx.AsyncClient(timeout=15.0, trust_env=False) as client:
        resp = await client.get(f"{base}/models", headers={"Authorization": f"Bearer {key}"})
        print("GET /models:", resp.status_code)
        assert resp.status_code == 200, f"GET /models 失败：{resp.status_code} {resp.text[:200]}"
        ids = [m.get("id") for m in resp.json().get("data", [])]
        print("models:", ids)
        assert ids, "无可用模型"
        model_name = ids[0]

    # 2. 远程压缩
    client = httpx.AsyncClient(timeout=httpx.Timeout(60.0), trust_env=False)
    model = OpenAIResponsesModel(
        model_name,
        provider=OpenAIProvider(api_key=key, base_url=base, http_client=client),
    )
    ctx = ModelRequestContext(
        model=model,
        messages=_history_from_fixture(),
        model_settings=ModelSettings(),
        model_request_parameters=ModelRequestParameters(),
    )
    try:
        response = await model.compact_messages(ctx)
        parts = response.parts
        print("compact_messages OK")
        print("parts:", [type(p).__name__ for p in parts])
        for p in parts:
            if type(p).__name__ == "CompactionPart":
                print("has_content:", p.has_content())
                print("provider_name:", p.provider_name)
                print("details keys:", list((p.provider_details or {}).keys()))
    except Exception as exc:
        print(f"compact_messages FAILED（记录，不判失败）：{type(exc).__name__}: {exc}")
        body = getattr(exc, "body", None)
        if body:
            print("body:", str(body)[:500])
    finally:
        await client.aclose()
