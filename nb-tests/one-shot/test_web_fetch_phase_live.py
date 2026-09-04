"""web_fetch 阶段耗时 live 测试：网络各阶段 vs LLM 摘要。

运行：

    ONE_SHOT_LIVE=1 uv run pytest nb-tests/one-shot/test_web_fetch_phase_live.py -s -q
    # 直接指定 URL（跳过搜索）：改 fixtures/web_fetch_phase.json 的 urls 列表

背景：latency 探针发现「明日方舟第十四章讲了什么」链路里 web_fetch 单步 61.8s
却只带回约 500 字符。web_fetch 默认 summarize=True：先抓 50K 原文，再调
``compaction.summarize_text`` 用当前 provider 做 LLM 摘要——这是 agent 图外的
隐藏模型请求（约 3 万+ token 输入），主链路观测不到。本探针把两段分开计时：

1. 网络阶段（与 web_fetch 同参数）：DNS → 连接+TLS+首字节（TTFB）→ 下载 →
   markdown 转换 → 8K 截断；
2. LLM 摘要阶段：``compaction.summarize_text``（50K 原文 → 当前 provider）。

问题与候选 URL 在 fixtures/web_fetch_phase.json（urls 为空时用 web_search 拿
候选）。报告落 agent-plan-report/web-fetch-phase-probe.md。
"""

from __future__ import annotations

import asyncio
import os
import re
import time
from typing import Any
from urllib.parse import urlparse

import pytest
from _live import build_deps, load_config, load_fixture, write_report

pytestmark = [
    pytest.mark.skipif(
        not os.environ.get("ONE_SHOT_LIVE"),
        reason="联网探针：设置 ONE_SHOT_LIVE=1 才运行",
    ),
]

PROBE_SCOPE = "probe:web-fetch-phase"
_FIXTURE = load_fixture("web_fetch_phase")

_URL_RE = re.compile(r"https?://[^\s)）\]》>\"']+")


async def _search_urls(config: Any) -> list[str]:
    """用 web_search 的同一配置搜问题，提取候选 URL。"""
    from urllib.parse import urlparse

    from hoshino.ai import provider, search

    cfg = search.resolve_search_config(PROBE_SCOPE, config)
    if cfg is None:
        return []
    proxy = provider.resolve_tool_proxy(config.proxy, tool_use_proxy=config.tool_use_proxy)
    text = await search.search_web(
        cfg, _FIXTURE["question"], proxy=proxy, verify=config.web_fetch_verify_ssl
    )
    urls: list[str] = []
    for raw in _URL_RE.findall(text):
        url = raw.rstrip(".,;!?")
        if url not in urls and urlparse(url).hostname:
            urls.append(url)
    return urls[:5]


async def _probe_network(url: str, *, verify: bool, proxy: str | None) -> dict[str, Any]:
    """与 web_fetch 同参数的抓取，分阶段计时。

    connect_ttfb_ms ≈ DNS（未缓存）+ TCP + TLS + 服务端处理 + 首字节
    （httpx 的 request hook 在连接建立前、response hook 在响应头到达时触发）。
    """
    import httpx
    from markdownify import markdownify as _to_markdown

    from hoshino.ai.tools.web.web_fetch import _DEFAULT_UA, _truncate_at_boundary

    phases: dict[str, Any] = {"url": url}
    parsed = urlparse(url)
    host = parsed.hostname
    port = 443 if parsed.scheme == "https" else 80

    dns_t0 = time.perf_counter()
    try:
        await asyncio.get_running_loop().getaddrinfo(host, port)
        phases["dns_ms"] = (time.perf_counter() - dns_t0) * 1000
    except OSError as exc:
        return {"url": url, "error": f"DNS 失败: {exc}"}

    events: dict[str, float] = {}

    async def on_request(request: httpx.Request) -> None:
        events["request"] = time.perf_counter()

    async def on_response(response: httpx.Response) -> None:
        events["response"] = time.perf_counter()

    headers = {
        "Accept": "text/markdown, text/html;q=0.9, */*;q=0.8",
        "User-Agent": _DEFAULT_UA,
    }
    http_t0 = time.perf_counter()
    try:
        async with (
            httpx.AsyncClient(
                trust_env=False,
                verify=verify,
                proxy=proxy,
                timeout=httpx.Timeout(30.0),
                follow_redirects=True,
                event_hooks={"request": [on_request], "response": [on_response]},
            ) as client,
            client.stream("GET", url, headers=headers) as response,
        ):
            phases["status"] = response.status_code
            phases["content_type"] = response.headers.get("content-type", "").split(";")[0]
            download_t0 = time.perf_counter()
            chunks = [chunk async for chunk in response.aiter_bytes()]
            phases["download_ms"] = (time.perf_counter() - download_t0) * 1000
    except httpx.HTTPError as exc:
        phases["error"] = f"HTTP 失败 {type(exc).__name__}: {exc}"
        phases["http_ms"] = (time.perf_counter() - http_t0) * 1000
        return phases
    phases["http_ms"] = (time.perf_counter() - http_t0) * 1000
    if "request" in events and "response" in events:
        phases["connect_ttfb_ms"] = (events["response"] - events["request"]) * 1000

    body = b"".join(chunks)
    phases["bytes"] = len(body)
    text = body.decode("utf-8", "replace")
    md_t0 = time.perf_counter()
    markdown = _to_markdown(text)
    phases["markdown_ms"] = (time.perf_counter() - md_t0) * 1000
    phases["md_chars"] = len(markdown)
    phases["truncated_chars"] = len(_truncate_at_boundary(markdown, 8_000))
    return phases


async def _probe_summarize(deps: Any, url: str, config: Any) -> dict[str, Any]:
    """复刻 web_fetch 的摘要分支：50K 原文 → summarize_text（隐藏的模型请求）。"""
    from hoshino.ai import compaction, provider
    from hoshino.ai.tools.web.web_fetch import (
        _DEFAULT_UA,
        _SUMMARY_SOURCE_MAX,
        fetch_url_to_markdown,
    )

    proxy = provider.resolve_tool_proxy(config.proxy, tool_use_proxy=config.tool_use_proxy)
    fetch_t0 = time.perf_counter()
    original = await fetch_url_to_markdown(
        url,
        verify_ssl=config.web_fetch_verify_ssl,
        max_chars=_SUMMARY_SOURCE_MAX,
        proxy=proxy,
        extra_headers={"User-Agent": _DEFAULT_UA},
    )
    fetch_seconds = time.perf_counter() - fetch_t0
    if len(original) <= 8_000:
        return {
            "skipped": True,
            "reason": f"原文仅 {len(original)} 字符，真实链路不会触发 LLM 摘要",
        }
    sum_t0 = time.perf_counter()
    summary = await compaction.summarize_text(deps, original)
    return {
        "skipped": False,
        "fetch_50k_seconds": fetch_seconds,
        "original_chars": len(original),
        "summary_seconds": time.perf_counter() - sum_t0,
        "summary_chars": len(summary or ""),
    }


def _fmt_network(phases: dict[str, Any]) -> str:
    if "error" in phases:
        return f"FAIL {phases['error']}"
    return (
        f"status={phases.get('status')} dns={phases.get('dns_ms', 0):.0f}ms "
        f"conn+ttfb={phases.get('connect_ttfb_ms', 0):.0f}ms "
        f"download={phases.get('download_ms', 0):.0f}ms "
        f"md={phases.get('markdown_ms', 0):.0f}ms "
        f"总={phases.get('http_ms', 0):.0f}ms "
        f"bytes={phases.get('bytes', 0):,} md_chars={phases.get('md_chars', 0):,}"
    )


async def test_network_phases_then_summary():
    """候选 URL 逐个分阶段计时，再对最大页跑 LLM 摘要；断言至少一个 URL 成功。"""
    from hoshino.ai import provider

    config = load_config()
    provider_id = config.default
    record = provider.get_provider(provider_id)
    assert record is not None, f"provider `{provider_id}` 不存在于 aichat.db"
    model = provider.resolve_text_model(PROBE_SCOPE, provider_id)
    if isinstance(model, tuple):
        _, model = model
    assert model, f"provider `{provider_id}` 未配置文本模型"
    deps = build_deps(config, provider_id, model, PROBE_SCOPE)

    tool_proxy = provider.resolve_tool_proxy(config.proxy, tool_use_proxy=config.tool_use_proxy)
    print(f"provider={provider_id} model={model}")
    print(f"tool_use_proxy={config.tool_use_proxy} → 抓取{'走配置代理' if tool_proxy else '直连'}")

    urls = _FIXTURE.get("urls") or await _search_urls(config)
    assert urls, "没有可抓取的 URL（未配置搜索 provider 且 fixtures urls 为空）"
    print(f"候选 URL 共 {len(urls)} 个：")
    for url in urls:
        print(f"  {url}")

    network_results: list[dict[str, Any]] = []
    for url in urls:
        print(f"\n== 网络阶段 {url} ==", flush=True)
        phases = await _probe_network(url, verify=config.web_fetch_verify_ssl, proxy=tool_proxy)
        network_results.append(phases)
        print(_fmt_network(phases), flush=True)
    assert any("error" not in r for r in network_results), "所有 URL 的网络阶段都失败"

    summary_result: dict[str, Any] | None = None
    candidates = [r for r in network_results if r.get("md_chars", 0) > 8_000]
    if candidates:
        target = max(candidates, key=lambda r: r["md_chars"])
        print(f"\n== LLM 摘要阶段（原文最大的 {target['url']}）==", flush=True)
        summary_result = await _probe_summarize(deps, target["url"], config)
        if summary_result.get("skipped"):
            print(f"跳过：{summary_result['reason']}")
        else:
            print(
                f"50K 原文抓取={summary_result['fetch_50k_seconds']:.1f}s "
                f"原文 {summary_result['original_chars']:,} 字符 | "
                f"LLM 摘要={summary_result['summary_seconds']:.1f}s "
                f"摘要 {summary_result['summary_chars']} 字符"
            )
    else:
        print("\n无超过 8000 字符的页面，真实链路不会触发 LLM 摘要")

    lines = [
        "# web_fetch 阶段耗时探针",
        "",
        f"- 时间：{time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"- provider：{provider_id} / {model}",
        f"- 抓取代理：{'配置代理' if tool_proxy else '直连'}",
        f"- 问题：{_FIXTURE['question']}",
        "",
        "## 网络阶段（与 web_fetch 同参数）",
        "",
        "| URL | status | dns | conn+ttfb | download | markdown | 总 | bytes | md_chars |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for r in network_results:
        if "error" in r:
            lines.append(f"| {r['url']} | FAIL | {r['error']} | | | | | | |")
            continue
        lines.append(
            f"| {r['url']} | {r.get('status')} | {r.get('dns_ms', 0):.0f}ms | "
            f"{r.get('connect_ttfb_ms', 0):.0f}ms | {r.get('download_ms', 0):.0f}ms | "
            f"{r.get('markdown_ms', 0):.0f}ms | {r.get('http_ms', 0):.0f}ms | "
            f"{r.get('bytes', 0):,} | {r.get('md_chars', 0):,} |"
        )
    if summary_result and not summary_result.get("skipped"):
        lines += [
            "",
            "## LLM 摘要阶段（隐藏模型请求）",
            "",
            f"- 50K 原文抓取：{summary_result['fetch_50k_seconds']:.1f}s",
            f"- 原文：{summary_result['original_chars']:,} 字符",
            f"- summarize_text（当前 provider）：{summary_result['summary_seconds']:.1f}s",
            f"- 摘要：{summary_result['summary_chars']} 字符",
        ]
    write_report("web-fetch-phase-probe.md", lines)
