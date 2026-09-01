"""zssm 结构化输出探针：真实 provider + ZssmOutput 强格式化验证。

运行方式：

    ONE_SHOT_LIVE=1 uv run pytest nb-tests/one-shot/test_zssm_structured_live.py -s -q

对运行时 DB 里配置的每个 text provider，发送 zssm 解释请求，
验证 Agent + ZssmOutput 结构化输出能正确返回 keywords/output/blocked 字段。
"""

from __future__ import annotations

import asyncio
import json
import os

import pytest

pytestmark = [
    pytest.mark.skipif(
        not os.environ.get("ONE_SHOT_LIVE"),
        reason="临时联网探针：设置 ONE_SHOT_LIVE=1 才运行",
    ),
]

_TEST_PROMPTS = [
    "RTX 5090 和 RTX 4090 有什么区别",
    "什么是量子纠缠",
]


async def test_zssm_structured_output_live():
    """对每个 provider 发 zssm 请求，验证 ZssmOutput 结构化输出。"""
    from nonebot_plugin_alconna.uniseg import Target
    from pydantic_ai.usage import UsageLimits

    from hoshino.ai import provider, runner
    from hoshino.ai import store as ai_store
    from hoshino.ai.config import AIConfig
    from hoshino.ai.deps import AgentDeps, PermissionSnapshot, Telemetry
    from hoshino.modules.ai.zssm import ZssmOutput, _build_zssm_agent

    config = AIConfig()
    rows = ai_store.list_provider_rows() or []
    if not rows:
        print("\n⚠️  DB 无 provider，跳过")
        return

    print(f"\n共 {len(rows)} 个 provider，开始 zssm 结构化输出探针...")
    results: list[dict] = []

    for row in rows:
        record = provider.ProviderRecord.from_row(row)
        effective_proxy = provider.resolve_effective_proxy(record, config.proxy)
        # model-list 注册表已移除：可用模型一律经 provider API 实时获取。
        available = await provider.fetch_available_models(
            record, proxy=effective_proxy, verify=config.web_fetch_verify_ssl
        )
        text_models = available or []
        if not text_models:
            print(f"  [{record.id}] 无法获取可用模型，跳过")
            continue
        text_model = text_models[0]

        for prompt_text in _TEST_PROMPTS:
            payload = {"target": prompt_text, "focus": "", "image_descriptions": ""}
            user_prompt = json.dumps(payload, ensure_ascii=False)

            try:
                agent = _build_zssm_agent(record, text_model, proxy=effective_proxy)
                # 构造最小 deps（zssm web 工具需要 surface/config/permissions）
                scope_key = f"probe:{record.id}"
                deps = AgentDeps(
                    surface="chat",
                    scope_key=scope_key,
                    target=Target.user("0"),
                    config=config,
                    permissions=PermissionSnapshot(is_superuser=False, is_admin=False),
                    bot=None,
                    event=None,
                    telemetry=Telemetry(
                        provider_id=record.id,
                        scope_key=scope_key,
                        model=text_model,
                    ),
                )
                result = await asyncio.wait_for(
                    runner.run_agent(
                        agent,
                        user_prompt,
                        deps=deps,
                        usage_limits=UsageLimits(request_limit=6),
                    ),
                    timeout=90.0,
                )

                if result is None:
                    status = "❌ result=None"
                    results.append(
                        {
                            "provider": record.id,
                            "model": text_model,
                            "prompt": prompt_text,
                            "status": status,
                        }
                    )
                    print(f"  [{record.id}/{text_model}] {prompt_text[:30]}... → {status}")
                    continue

                out: ZssmOutput = result.output
                usage = result.usage
                kw_count = len(out.keywords)
                out_len = len(out.output)
                blocked = out.blocked

                # 验证结构化字段
                errors = []
                if not isinstance(out, ZssmOutput):
                    errors.append(f"output type={type(out).__name__}, expected ZssmOutput")
                if not blocked and kw_count == 0:
                    errors.append("keywords 为空但 blocked=False")
                if not blocked and out_len == 0:
                    errors.append("output 为空但 blocked=False")

                status = "✅" if not errors else f"⚠️ {errors}"
                entry = {
                    "provider": record.id,
                    "model": text_model,
                    "prompt": prompt_text,
                    "keywords": out.keywords,
                    "output_len": out_len,
                    "blocked": blocked,
                    "input_tokens": getattr(usage, "input_tokens", 0),
                    "output_tokens": getattr(usage, "output_tokens", 0),
                    "cache_read": getattr(usage, "cache_read_tokens", 0),
                    "status": status,
                }
                results.append(entry)
                print(
                    f"  [{record.id}/{text_model}] {prompt_text[:30]}... → "
                    f"{status} kw={out.keywords} out={out_len}c "
                    f"in={getattr(usage, 'input_tokens', 0)} out={getattr(usage, 'output_tokens', 0)} "
                    f"cache={getattr(usage, 'cache_read_tokens', 0)}"
                )
            except Exception as exc:
                status = f"❌ {type(exc).__name__}: {exc}"
                results.append(
                    {
                        "provider": record.id,
                        "model": text_model,
                        "prompt": prompt_text,
                        "status": status,
                    }
                )
                print(f"  [{record.id}/{text_model}] {prompt_text[:30]}... → {status}")

    # 汇总
    ok = sum(1 for r in results if r.get("status", "").startswith("✅"))
    total = len(results)
    print(f"\n📊 汇总: {ok}/{total} 通过")
    if ok < total:
        for r in results:
            if not r.get("status", "").startswith("✅"):
                print(
                    f"  ❌ {r['provider']}/{r.get('model', '?')} {r.get('prompt', '')[:30]} → {r['status']}"
                )
    assert ok > 0, "所有探针均失败"
