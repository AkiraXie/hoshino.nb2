"""web/web_fetch：抓取网页正文为 markdown（自实现，替代 pydantic-ai common_tools）。

pydantic-ai 的 ``web_fetch_tool`` 用 httpx 默认客户端（``trust_env=True`` +
``verify=True``）：在本环境会命中 socks 代理解析失败（``ALL_PROXY=socks://…``）与
证书链缺失（仓库已在 ``hoshino/util/playwrights.py`` 全局
``ssl._create_unverified_context``）。这里改用 ``trust_env=False`` + 可配置 verify，
并保留最基本的 SSRF 防护（拒绝私有/回环/保留地址）。

工具语义：仅当模型已知具体网址、需要其全文时才用；一般了解信息优先用
``duckduckgo_search``。
"""

from __future__ import annotations

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

_MAX_CHARS = 50_000
_ALLOWED_SCHEMES = ("http", "https")


async def fetch_url_to_markdown(
    url: str,
    *,
    verify_ssl: bool = True,
    max_chars: int = _MAX_CHARS,
    proxy: str | None = None,
) -> str:
    """抓取网页正文转 markdown（供 web_fetch 工具与 zssm 插件复用）。

    ``verify_ssl``：HTTPS 证书校验开关（默认校验）；SSRF 防护（拒绝私有/回环/
    保留地址）内建于本函数。``proxy``：抓取请求代理（``AI_TOOL_USE_PROXY``
    开启时由调用方传入；``trust_env=False`` 仍忽略环境变量代理）。
    """
    parsed = urlparse(url)
    if parsed.scheme not in _ALLOWED_SCHEMES or not parsed.hostname:
        return "仅支持 http/https 网址。"
    if await is_private_host(parsed.hostname):
        return "拒绝访问私有/内网地址。"

    headers = {"Accept": "text/markdown, text/html;q=0.9, */*;q=0.8"}
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
    text = response.text
    if content_type in ("text/markdown", "text/x-markdown"):
        content = text
    elif content_type in ("", "text/html", "application/xhtml+xml"):
        content = _to_markdown(text) if _to_markdown is not None else text
    else:
        content = text

    if len(content) > max_chars:
        content = content[:max_chars] + "\n\n[内容已截断]"
    return content.strip() or "（空内容）"


async def web_fetch(ctx: RunContext[AgentDeps], url: str) -> str:
    """抓取指定网址的网页正文并转为 markdown。

    仅当你已经知道某个具体网址、需要它的全文时才用；只是想了解信息请优先用
    duckduckgo_search。禁止访问私有/内网地址。
    """
    return await fetch_url_to_markdown(
        url,
        verify_ssl=ctx.deps.config.web_fetch_verify_ssl,
        proxy=provider.resolve_tool_proxy(
            ctx.deps.config.proxy, tool_use_proxy=ctx.deps.config.tool_use_proxy
        ),
    )


# markdownify 缺失时置 None：注册表据此跳过注入（与其它可选依赖工具一致）。
tool = web_fetch if _to_markdown is not None else None
