"""搜索 provider 领域层：deepseek / tavily / 博查 三种，与聊天 provider 解耦。

与 vision 同思路：搜索单独配置（``ai search`` 命令 + ``ai_search_providers``
单行表），不再依赖聊天 provider 的 kind。三种内置 provider：

- ``deepseek``：Anthropic 兼容 Messages 端点 + 服务端 ``web_search_20250305``
  工具（dsh 同款 wire format），响应解析 ``web_search_tool_result`` 块与
  ``text`` 块的 ``citations``；
- ``tavily``：``POST {url}/search``，Bearer 鉴权，``results[].title/url/content``；
- ``bocha``（博查）：``POST {url}/v1/web-search``，Bearer 鉴权，
  ``webPages.value[].name/url/snippet``（兼容 Bing 格式）。

默认 deepseek：未配置时继承当前 anthropic 聊天 provider 的 url/key/model
（存量 DeepSeek 用户零配置可用）；没有可用 anthropic provider 时返回 None，
由调用方提示 ``ai search set``。代理语义与 web_fetch 等工具一致
（``AI_TOOL_USE_PROXY`` 开启才走 AI 代理，见 ``provider.resolve_tool_proxy``）。
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from . import store
from .config import AIConfig

SEARCH_KINDS = ("deepseek", "tavily", "bocha")

DEFAULT_DEEPSEEK_URL = "https://api.deepseek.com/anthropic/v1"
DEFAULT_DEEPSEEK_MODEL = "deepseek-v4-flash"
DEFAULT_TAVILY_URL = "https://api.tavily.com"
DEFAULT_BOCHA_URL = "https://api.bocha.cn"

_TIMEOUT = httpx.Timeout(30.0)
_USER_AGENT = "hoshino-nb2/0.1"


@dataclass(frozen=True, slots=True)
class SearchConfig:
    """一次搜索请求的完整配置快照（已填充默认值）。"""

    kind: str
    url: str
    key: str
    model: str = ""


def _anthropic_chat_provider(scope_key: str | None, config: AIConfig):
    """当前 scope 的 anthropic kind 聊天 provider（deepseek 默认凭据继承源）。"""
    from . import provider
    from .base import resolve_provider

    provider_id = resolve_provider(scope_key, config)
    if provider_id is None:
        return None
    record = provider.get_provider(provider_id)
    return record if record is not None and record.kind == "anthropic" else None


def resolve_search_config(scope_key: str | None, config: AIConfig) -> SearchConfig | None:
    """解析当前搜索配置；未配置/kind 未知返回 None（由调用方提示配置）。"""
    row = store.get_search_provider_row()
    if row is None:
        # 默认 deepseek：继承 anthropic 聊天 provider 凭据。
        record = _anthropic_chat_provider(scope_key, config)
        if record is None:
            return None
        return SearchConfig(
            kind="deepseek",
            url=record.url or DEFAULT_DEEPSEEK_URL,
            key=record.key,
            model=record.default_text_model or DEFAULT_DEEPSEEK_MODEL,
        )
    kind = row["kind"]
    if kind == "deepseek":
        record = _anthropic_chat_provider(scope_key, config)
        return SearchConfig(
            kind="deepseek",
            url=row["url"] or DEFAULT_DEEPSEEK_URL,
            key=row["key"] or (record.key if record is not None else ""),
            model=(
                row["model"]
                or (record.default_text_model if record is not None else "")
                or DEFAULT_DEEPSEEK_MODEL
            ),
        )
    if kind == "tavily":
        return SearchConfig(kind="tavily", url=row["url"] or DEFAULT_TAVILY_URL, key=row["key"])
    if kind == "bocha":
        return SearchConfig(kind="bocha", url=row["url"] or DEFAULT_BOCHA_URL, key=row["key"])
    return None  # 未知 kind（数据异常）→ 视为未配置


async def search_web(
    cfg: SearchConfig,
    query: str,
    *,
    proxy: str | None = None,
    verify: bool = True,
) -> str:
    """按配置执行一次搜索，返回可读结果文本（不抛异常，失败返回错误提示）。"""
    if not cfg.key:
        return f"搜索 provider `{cfg.kind}` 缺少 API key：`ai search set {cfg.kind} --key <k>`。"
    match cfg.kind:
        case "deepseek":
            return await _deepseek_search(cfg, query, proxy=proxy, verify=verify)
        case "tavily":
            return await _tavily_search(cfg, query, proxy=proxy, verify=verify)
        case "bocha":
            return await _bocha_search(cfg, query, proxy=proxy, verify=verify)
    return f"未知搜索 provider kind：`{cfg.kind}`。"


def _socks5(proxy: str | None) -> str | None:
    """把 socks:// 归一化为 socks5://（httpx 可解析），与 LLM 请求路径一致。"""
    if proxy and proxy.startswith("socks://"):
        return f"socks5://{proxy.removeprefix('socks://')}"
    return proxy


async def _post_json(
    url: str,
    headers: dict[str, str],
    body: dict,
    *,
    proxy: str | None,
    verify: bool,
    fallback_url: str | None = None,
) -> tuple[httpx.Response | None, str]:
    """发一条 JSON POST，优先 ``url``、404/405 时回退 ``fallback_url``。

    返回 ``(response, last_error)``；网络失败时 response 为 None。
    """
    candidates = (url,) if fallback_url is None else (url, fallback_url)
    last_error = "无法连接"
    async with httpx.AsyncClient(
        proxy=_socks5(proxy),
        trust_env=False,
        verify=verify,
        timeout=_TIMEOUT,
        follow_redirects=False,
    ) as client:
        for candidate in candidates:
            try:
                response = await client.post(candidate, headers=headers, json=body)
            except (httpx.HTTPError, ValueError) as exc:
                last_error = f"{type(exc).__name__}"
                continue
            if response.status_code in (404, 405):
                last_error = f"HTTP {response.status_code}"
                continue  # 端点形态不对 → 试回退候选
            return response, ""
        return None, last_error


def _api_error(response: httpx.Response) -> str:
    """提取 API 错误详情（error.message / message）；失败给 HTTP 状态。"""
    try:
        payload = response.json()
    except ValueError:
        return f"搜索 API 错误（HTTP {response.status_code}）。"
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict) and error.get("message"):
            return f"搜索 API 错误（HTTP {response.status_code}）：{error['message']}"
        if error:
            return f"搜索 API 错误（HTTP {response.status_code}）：{error}"
        if payload.get("message"):
            return f"搜索 API 错误（HTTP {response.status_code}）：{payload['message']}"
    return f"搜索 API 错误（HTTP {response.status_code}）。"


# ---------------------------------------------------------------- deepseek


def _format_deepseek_results(data: dict) -> str:
    """解析 Messages 响应：web_search_tool_result 块 + text 块 citations → 可读文本。"""
    blocks = data.get("content") or []
    seen: set[str] = set()
    items: list[dict] = []
    for block in blocks:
        if block.get("type") != "web_search_tool_result":
            continue
        for item in block.get("content") or []:
            if item.get("type") != "web_search_result":
                continue
            url = item.get("url") or ""
            if url and url not in seen:
                seen.add(url)
                items.append(item)
    if not items:
        return "搜索未返回结果。"
    # 摘要来自 text 块的 citations（url → cited_text，首个出现优先）。
    snippets: dict[str, str] = {}
    for block in blocks:
        if block.get("type") != "text":
            continue
        for cite in block.get("citations") or []:
            url = cite.get("url") or ""
            text = cite.get("cited_text") or ""
            if url and text and url not in snippets:
                snippets[url] = text
    lines = [f"搜索结果（{len(items)} 条）："]
    for index, item in enumerate(items, start=1):
        url = item.get("url") or ""
        lines.append(f"{index}. {item.get('title') or url}\n   链接：{url}")
        if url in snippets:
            lines.append(f"   摘要：{snippets[url]}")
    return "\n".join(lines)


async def _deepseek_search(
    cfg: SearchConfig, query: str, *, proxy: str | None, verify: bool
) -> str:
    """向 anthropic 兼容端点发一条原生搜索请求（dsh 同款 wire format）。"""
    headers = {
        "x-api-key": cfg.key,
        "authorization": f"Bearer {cfg.key}",
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
        "accept": "application/json",
        "user-agent": _USER_AGENT,
    }
    body = {
        "model": cfg.model,
        "max_tokens": 4096,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": f"Perform a web search for the query: {query}"}
                ],
            }
        ],
        # 服务端 web_search 工具（Anthropic Messages；dsh 同款）。
        "tools": [{"type": "web_search_20250305", "name": "web_search", "max_uses": 5}],
    }
    base = cfg.url.rstrip("/")
    # base 可能带或不带 /v1（仓库约定两者都有），先试直接拼接。
    response, last_error = await _post_json(
        f"{base}/messages",
        headers,
        body,
        proxy=proxy,
        verify=verify,
        fallback_url=f"{base}/v1/messages",
    )
    if response is None:
        return f"原生搜索失败（{last_error}）。"
    if response.status_code >= 400:
        return _api_error(response)
    try:
        return _format_deepseek_results(response.json())
    except ValueError:
        return "原生搜索失败（响应解析失败）。"


# ---------------------------------------------------------------- tavily


def _format_tavily_results(data: dict) -> str:
    results = data.get("results") or []
    if not results:
        return "搜索未返回结果。"
    lines = [f"搜索结果（{len(results)} 条）："]
    for index, item in enumerate(results, start=1):
        if not isinstance(item, dict):
            continue
        url = item.get("url") or ""
        lines.append(f"{index}. {item.get('title') or url}\n   链接：{url}")
        content = (item.get("content") or "").strip()
        if content:
            lines.append(f"   摘要：{content}")
    return "\n".join(lines)


async def _tavily_search(cfg: SearchConfig, query: str, *, proxy: str | None, verify: bool) -> str:
    headers = {
        "authorization": f"Bearer {cfg.key}",
        "content-type": "application/json",
        "accept": "application/json",
        "user-agent": _USER_AGENT,
    }
    body = {"query": query, "search_depth": "basic", "max_results": 5}
    response, last_error = await _post_json(
        f"{cfg.url.rstrip('/')}/search", headers, body, proxy=proxy, verify=verify
    )
    if response is None:
        return f"搜索失败（{last_error}）。"
    if response.status_code >= 400:
        return _api_error(response)
    try:
        return _format_tavily_results(response.json())
    except ValueError:
        return "搜索失败（响应解析失败）。"


# ---------------------------------------------------------------- bocha


def _format_bocha_results(data: dict) -> str:
    pages = ((data.get("data") or {}).get("webPages") or {}).get("value") or []
    items = [page for page in pages if isinstance(page, dict)]
    if not items:
        return "搜索未返回结果。"
    lines = [f"搜索结果（{len(items)} 条）："]
    for index, item in enumerate(items, start=1):
        url = item.get("url") or ""
        lines.append(f"{index}. {item.get('name') or url}\n   链接：{url}")
        snippet = (item.get("snippet") or "").strip()
        if snippet:
            lines.append(f"   摘要：{snippet}")
    return "\n".join(lines)


async def _bocha_search(cfg: SearchConfig, query: str, *, proxy: str | None, verify: bool) -> str:
    headers = {
        "authorization": f"Bearer {cfg.key}",
        "content-type": "application/json",
        "accept": "application/json",
        "user-agent": _USER_AGENT,
    }
    body = {"query": query, "count": 5, "freshness": "noLimit"}
    response, last_error = await _post_json(
        f"{cfg.url.rstrip('/')}/v1/web-search", headers, body, proxy=proxy, verify=verify
    )
    if response is None:
        return f"搜索失败（{last_error}）。"
    if response.status_code >= 400:
        return _api_error(response)
    try:
        data = response.json()
    except ValueError:
        return "搜索失败（响应解析失败）。"
    if data.get("code") != 200:
        return f"博查搜索错误：{data.get('msg') or data.get('code')}"
    return _format_bocha_results(data)
