"""web/image_view：抓取图片 URL，返回规范为 JPEG/PNG 的 BinaryContent 列表。

网络行为与 web_fetch 一致：``trust_env=False``（规避 socks 环境变量崩溃）、
``verify=config.web_fetch_verify_ssl``、SSRF 防护（拒绝私有/回环/保留地址）、
30s 超时、跟随重定向。图片先按字节判定真实格式并规范为 JPEG/PNG（webp/avif
等重新编码，带透明存 PNG，否则 JPEG）；动图抽首/中/尾代表帧当多张静态图返回
（OpenAI vision 只接受 non-animated GIF）。处理后仍超限才拒绝，失败返回错误
提示字符串。
"""

from __future__ import annotations

from urllib.parse import urlparse

from pydantic_ai import BinaryContent, RunContext

from hoshino.ai.net import is_private_host

from ... import media, provider
from ...deps import AgentDeps

_ALLOWED_SCHEMES = ("http", "https")


async def fetch_image_as_content(
    url: str,
    *,
    verify_ssl: bool,
    fetch_proxy: str | None = None,
) -> list[BinaryContent] | str:
    """抓取图片 URL 并规范为 BinaryContent 列表（动图抽代表帧，供其它入口复用）。"""
    return await media.fetch_image_url(url, verify_ssl=verify_ssl, proxy=fetch_proxy)


async def image_view(ctx: RunContext[AgentDeps], url: str):
    """抓取指定 URL 的图片并返回图片内容（供当前模型直接看图）。

    动图返回多张代表帧（按时间先后）。仅当需要查看具体图片 URL 的内容时使用；
    禁止访问私有/内网地址。成功返回 BinaryContent 列表；失败返回错误提示字符串。
    """
    parsed = urlparse(url)
    if parsed.scheme not in _ALLOWED_SCHEMES or not parsed.hostname:
        return "仅支持 http/https 图片 URL。"
    if await is_private_host(parsed.hostname):
        return "拒绝访问私有/内网地址。"

    return await fetch_image_as_content(
        url,
        verify_ssl=ctx.deps.config.web_fetch_verify_ssl,
        fetch_proxy=provider.resolve_tool_proxy(
            ctx.deps.config.proxy, tool_use_proxy=ctx.deps.config.tool_use_proxy
        ),
    )


tool = image_view
