"""web/web_fetch：抓取网页正文为 markdown（自实现，替代 pydantic-ai common_tools）。

pydantic-ai 的 ``web_fetch_tool`` 用 httpx 默认客户端（``trust_env=True`` +
``verify=True``）：在本环境会命中 socks 代理解析失败（``ALL_PROXY=socks://…``）与
证书链缺失（仓库已在 ``hoshino/util/playwrights.py`` 全局
``ssl._create_unverified_context``）。这里改用 ``trust_env=False`` + 可配置 verify，
并保留最基本的 SSRF 防护（拒绝私有/回环/保留地址）。

工具语义：仅当模型已知具体网址、需要它的全文时才用；一般了解信息优先用
``web_search``（provider 原生联网搜索）。支持按需自定义请求头（User-Agent 等）
以应对反爬站点（如微信公众号）。
"""

from __future__ import annotations

import json
from urllib.parse import urlparse

import httpx
from pydantic_ai import RunContext

from ... import provider
from ...deps import AgentDeps
from .net import is_private_host

try:
    from markdownify import markdownify as _to_markdown
except ImportError:  # markdownify 未安装 → 工具不注入
    _to_markdown = None

_MAX_CHARS = 24_000
# 摘要分支抓取原文的上限（须高于 web_fetch_max_chars，摘要才只在超长时触发）。
_SUMMARY_SOURCE_MAX = 32_000
_ALLOWED_SCHEMES = ("http", "https")
_DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)


async def fetch_url_to_markdown(
    url: str,
    *,
    verify_ssl: bool = True,
    max_chars: int = _MAX_CHARS,
    proxy: str | None = None,
    extra_headers: dict[str, str] | None = None,
) -> str:
    """抓取网页正文转 markdown（供 web_fetch 工具与 zssm 插件复用）。

    ``verify_ssl``：HTTPS 证书校验开关（默认校验）；SSRF 防护（拒绝私有/回环/
    保留地址）内建于本函数。``proxy``：抓取请求代理（``AI_TOOL_USE_PROXY``
    开启时由调用方传入；``trust_env=False`` 仍忽略环境变量代理）。
    ``extra_headers``：额外请求头，与默认 Accept 合并（同名覆盖默认值）；
    用于应对反爬站点（如微信公众号需设置 User-Agent）。
    """
    parsed = urlparse(url)
    if parsed.scheme not in _ALLOWED_SCHEMES or not parsed.hostname:
        return "仅支持 http/https 网址。"
    if await is_private_host(parsed.hostname):
        return "拒绝访问私有/内网地址。"

    headers: dict[str, str] = {"Accept": "text/markdown, text/html;q=0.9, */*;q=0.8"}
    if extra_headers:
        headers.update(extra_headers)

    async with httpx.AsyncClient(
        trust_env=False,
        verify=verify_ssl,
        proxy=proxy,
        timeout=httpx.Timeout(30.0),
        follow_redirects=True,
    ) as client:
        try:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
        except (httpx.HTTPError, ValueError) as exc:
            return f"抓取失败（{type(exc).__name__}）。"

    content_type = response.headers.get("content-type", "").split(";")[0].strip().lower()
    if content_type == "application/pdf" or urlparse(url).path.lower().endswith(".pdf"):
        return "这是 PDF 文件，请使用 file_view 读取，不要使用 web_fetch。"
    text = response.text
    if content_type in ("text/markdown", "text/x-markdown"):
        content = text
    elif content_type in ("", "text/html", "application/xhtml+xml"):
        content = _to_markdown(text) if _to_markdown is not None else text
    else:
        content = text

    content = _truncate_at_boundary(content, max_chars)
    return content.strip() or "（空内容）"


def _truncate_at_boundary(content: str, max_chars: int) -> str:
    """Limit markdown without cutting a paragraph or heading in half."""
    if max_chars <= 0 or len(content) <= max_chars:
        return content
    candidate = content[:max_chars]
    boundary = max(candidate.rfind("\n\n"), candidate.rfind("\n#"))
    if boundary < max_chars // 2:
        boundary = max_chars
    return content[:boundary].rstrip() + "\n\n[内容已截断；如需细节请再次 fetch 原文]"


def _parse_extra_headers(raw: str) -> dict[str, str]:
    """解析用户传入的请求头字符串为字典。

    支持两种格式：
    - JSON 对象：``{"User-Agent": "...", "Referer": "..."}``
    - Key: Value 逐行文本（兼容 LLM 非 JSON 输出）
    """
    raw = raw.strip()
    if not raw:
        return {}
    # 尝试 JSON 解析
    if raw.startswith("{"):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return {str(k): str(v) for k, v in parsed.items()}
        except json.JSONDecodeError:
            pass
    # 回退：按行解析 Key: Value
    result: dict[str, str] = {}
    for raw_line in raw.splitlines():
        stripped = raw_line.strip()
        if ":" in stripped:
            key, _, value = stripped.partition(":")
            key = key.strip()
            value = value.strip()
            if key:
                result[key] = value
    return result


async def web_fetch(
    ctx: RunContext[AgentDeps],
    url: str,
    user_agent: str = "",
    extra_headers: str = "",
    max_chars: int | None = None,
    summarize: bool = True,
) -> str:
    """抓取指定网址的网页正文并转为 markdown。

    仅当你已经知道某个具体网址、需要它的全文时才用；只是想了解信息请优先用
    web_search。禁止访问私有/内网地址。

    Args:
        url: 要抓取的网页 URL。
        user_agent: 自定义 User-Agent。留空使用内置浏览器 UA（可应对多数反爬）；
            微信公众号等站点通常需要设置此项。示例：
            "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/125.0 Mobile"
        extra_headers: 额外 HTTP 请求头（JSON 对象或 Key: Value 逐行文本），
            与默认 Accept 合并。示例：{"Referer": "https://mp.weixin.qq.com/"}
        max_chars: 返回正文的最大字符数，默认 8000；需要更多细节时可调大。
        summarize: 超长正文是否先用轻量模型提取关键事实，默认开启。
    """
    headers: dict[str, str] = {}
    # 始终设置 UA：未指定时用内置浏览器 UA（比 httpx 默认 python-httpx/x.x 更不易被拦）
    ua = user_agent.strip() if user_agent else _DEFAULT_UA
    headers["User-Agent"] = ua

    if extra_headers:
        parsed = _parse_extra_headers(extra_headers)
        headers.update(parsed)

    verify_ssl = ctx.deps.config.web_fetch_verify_ssl
    effective_max_chars = max_chars or ctx.deps.config.web_fetch_max_chars
    proxy = provider.resolve_tool_proxy(
        ctx.deps.config.proxy, tool_use_proxy=ctx.deps.config.tool_use_proxy
    )
    if summarize and ctx.deps.config.web_fetch_summarize:
        from ... import compaction

        original = await fetch_url_to_markdown(
            url,
            verify_ssl=verify_ssl,
            max_chars=_SUMMARY_SOURCE_MAX,
            proxy=proxy,
            extra_headers=headers,
        )
        if len(original) > effective_max_chars:
            summary = await compaction.summarize_text(ctx.deps, original)
            if summary:
                return f"{summary}\n\n[原文：{url}]"
    return await fetch_url_to_markdown(
        url,
        verify_ssl=verify_ssl,
        max_chars=effective_max_chars,
        proxy=proxy,
        extra_headers=headers,
    )


# markdownify 缺失时置 None：注册表据此跳过注入（与其它可选依赖工具一致）。
tool = web_fetch if _to_markdown is not None else None
