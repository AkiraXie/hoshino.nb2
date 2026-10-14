"""file_view 路径 live 探针：真实 provider 下验证溢出目录可读 + 越界路径软失败。

运行：

    ONE_SHOT_LIVE=1 uv run pytest nb-tests/one-shot/test_file_view_paths_live.py -s -q

覆盖两件事（对应历史上的真实故障：模型被溢出提示引去读 ``data/ai_tool_overflow``
却读不到，``ValueError`` 逃逸出工具把整轮 run 杀掉）：

1. 溢出目录可读：让模型对真实的溢出落盘文件调 ``file_view``，从消息历史里的
   ``ToolReturnPart`` 断言读到了文件内容（不是错误文本）。
2. 越界路径软失败：让模型对 ``/etc/hostname`` 调 ``file_view``，断言整轮正常结束
   （没有任何异常抛出）、工具返回是「读取失败：ValueError：路径不在允许的…」。

只打印脱敏信息（文件名的 hash 部分、长度、工具名），不落 key/token。
"""

from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path

import pytest
from _live import (
    PROBE_RUN_TIMEOUT_SECONDS,
    build_agent,
    build_deps,
    load_config,
    write_report,
)

pytestmark = [
    pytest.mark.skipif(
        not os.environ.get("ONE_SHOT_LIVE"),
        reason="联网探针：设置 ONE_SHOT_LIVE=1 才运行",
    ),
]

PROBE_SCOPE = "probe:file-view-paths-live"

#: 越界路径：不在附件目录 / 工作目录 / 工具输出目录内（必然被白名单拒绝）。
_OUT_OF_SCOPE_PATH = "/etc/hostname"


def _newest_overflow_file() -> Path:
    """取真实溢出目录里最新的落盘文件（没有则跳过：需要先有工具结果溢出）。"""
    from hoshino.ai import paths

    config = load_config()
    root = paths.tool_overflow_dir(config)
    files = sorted(root.glob("tool_*.txt"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        pytest.skip(f"溢出目录为空：{root}（需先有工具返回超限的对话）")
    return files[0]


def _tool_returns(result) -> list[str]:
    """收集本轮所有工具返回文本（ToolReturnPart.content）。"""
    from pydantic_ai.messages import ToolReturnPart

    return [
        str(part.content)
        for message in result.all_messages()
        for part in getattr(message, "parts", []) or []
        if isinstance(part, ToolReturnPart)
    ]


async def _run_file_view(
    prompt: str, *, provider_id: str, model: str, record
) -> tuple[object, list[str]]:
    from hoshino.ai import runner

    config = load_config()
    agent = build_agent(config, provider_id, record, model)
    deps = build_deps(config, provider_id, model, PROBE_SCOPE)
    run_log = runner.RunLog()
    result = await asyncio.wait_for(
        runner.run_agent_with_retry(
            agent,
            prompt,
            deps=deps,
            message_history=[],
            run_log=run_log,
        ),
        timeout=PROBE_RUN_TIMEOUT_SECONDS,
    )
    assert result is not None, "模型没有返回内容"
    return result, _tool_returns(result)


def _prepare() -> tuple[str, str, object]:
    from hoshino.ai import provider, store

    store.ensure_schema()
    provider_id, model = provider.resolve_model(PROBE_SCOPE)
    record = provider.get_provider(provider_id) if provider_id else None
    assert record is not None and model, (
        "未配置默认模型（超级用户 `ai model default <provider> <模型>`）"
    )
    return provider_id, model, record


async def test_overflow_file_is_readable_by_file_view():
    """溢出目录内的落盘文件可被 file_view 读到（历史上被白名单拒绝并杀掉整轮）。"""
    overflow = _newest_overflow_file()
    expected_marker = overflow.read_text(encoding="utf-8").strip().splitlines()[0][:20]
    provider_id, model, record = _prepare()

    print("=" * 70)
    print(f"file_view 路径 live 探针（溢出目录可读）provider={provider_id} model={model}")
    print(f"文件：{overflow.parent.name}/{overflow.name[:12]}…（{overflow.stat().st_size:,}B）")
    print(f"断言标记（首行前 20 字）：{expected_marker}")

    started = time.perf_counter()
    result, returns = await _run_file_view(
        f"请调用 file_view 读取本地文件 {overflow}（不要用 web_fetch），"
        "然后原样告诉我该文件的第一行内容，不要编造。",
        provider_id=provider_id,
        model=model,
        record=record,
    )
    elapsed = time.perf_counter() - started

    print(f"[OK] 总耗时={elapsed:.1f}s 工具返回数={len(returns)}")
    for text in returns:
        print(f"  返回片段：{text[:60]!r}（{len(text)} 字符）")

    assert returns, "模型没有调用 file_view"
    assert any(expected_marker in text for text in returns), (
        f"工具返回里没有文件首行标记 {expected_marker!r}；返回：{[t[:80] for t in returns]}"
    )
    assert not any("读取失败" in text for text in returns), "溢出目录文件应能读取，不应返回读取失败"
    print(f"回复片段：{str(result.output)[:60]!r}")

    write_report(
        "file-view-paths-live.md",
        [
            "# file_view 路径 live 探针",
            "",
            "## 1. 溢出目录可读（data/ai_tool_overflow）",
            "",
            f"- provider/model：{provider_id}/{model}",
            f"- 文件：{overflow.parent.name}/tool_<hash>.txt（{overflow.stat().st_size:,}B）",
            f"- 结果：工具返回 {len(returns)} 条，含文件首行标记 `{expected_marker}`，耗时 {elapsed:.1f}s",
            "",
            "结论：溢出提示给出的路径现在可被 file_view 读到（白名单已纳入工具输出目录）。",
        ],
    )


async def test_out_of_scope_path_returns_error_text():
    """越界路径不再是致命异常：整轮正常结束，工具返回错误文本。"""
    provider_id, model, record = _prepare()

    print("=" * 70)
    print(f"file_view 路径 live 探针（越界路径软失败）provider={provider_id} model={model}")
    print(f"路径：{_OUT_OF_SCOPE_PATH}")

    started = time.perf_counter()
    result, returns = await _run_file_view(
        f"请调用 file_view 读取本地文件 {_OUT_OF_SCOPE_PATH}，"
        "把工具返回的内容原样复述给我（包括任何错误提示），不要编造。",
        provider_id=provider_id,
        model=model,
        record=record,
    )
    elapsed = time.perf_counter() - started

    print(f"[OK] 总耗时={elapsed:.1f}s（无异常逃逸，整轮完成）工具返回数={len(returns)}")
    for text in returns:
        print(f"  返回片段：{text[:80]!r}")

    assert returns, "模型没有调用 file_view"
    assert any("读取失败" in text and "路径不在允许" in text for text in returns), (
        f"越界路径应返回白名单错误文本；实际返回：{[t[:80] for t in returns]}"
    )
    print(f"回复片段：{str(result.output)[:60]!r}")

    write_report(
        "file-view-paths-live.md",
        [
            "# file_view 路径 live 探针",
            "",
            "## 2. 越界路径软失败（/etc/hostname）",
            "",
            f"- provider/model：{provider_id}/{model}",
            f"- 结果：整轮正常结束（无异常逃逸），工具返回含「读取失败：ValueError：路径不在允许的…」，"
            f"耗时 {elapsed:.1f}s",
            "",
            "结论：路径越界只回给模型错误文本，不再把整轮 run 打挂。",
        ],
    )
