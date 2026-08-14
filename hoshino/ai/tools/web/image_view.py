"""web/image_view：抓取图片并作为多模态内容返回给模型。

pydantic-ai 2.28 无内置 image_view common tool（官方后续版本才提供），这里自实现
同语义版本：http(s) URL → 抓取字节 → 返回 ``BinaryContent``。pydantic-ai 2.28 的
``ToolReturnContent`` 支持多模态文件（已实测），模型可直接"看到"图片。

网络行为与 web_fetch 一致：``trust_env=False``（规避 socks 环境变量崩溃）、
``verify=config.web_fetch_verify_ssl``、SSRF 防护（拒绝私有/回环/保留地址）、
30s 超时、跟随重定向。单图上限 15MB。
"""

from __future__ import annotations

from urllib.parse import urlparse

import httpx
from pydantic_ai import BinaryContent, RunContext

from ...deps import AgentDeps
from .net import is_private_host

_MAX_BYTES = 15 * 1024 * 1024
_ALLOWED_SCHEMES = ("http", "https")
_IMAGE_MEDIA_TYPES = ("image/png", "image/jpeg", "image/webp", "image/gif")


def _media_type_from_content_type(content_type: str | None) -> str:
    """从响应头推断图片 media_type；未知一律按 image/png 处理。"""
    if content_type:
        ct = content_type.split(";")[0].strip().lower()
        if ct in _IMAGE_MEDIA_TYPES:
            return ct
    return "image/png"


async def image_view(ctx: RunContext[AgentDeps], url: str):
    """抓取指定 URL 的图片并返回给模型查看。

    仅当需要查看具体图片 URL 的内容时使用；禁止访问私有/内网地址。
    """
    parsed = urlparse(url)
    if parsed.scheme not in _ALLOWED_SCHEMES or not parsed.hostname:
        return "仅支持 http/https 图片 URL。"
    if is_private_host(parsed.hostname):
        return "拒绝访问私有/内网地址。"

    config = ctx.deps.config
    async with httpx.AsyncClient(
        trust_env=False,
        verify=config.web_fetch_verify_ssl,
        timeout=httpx.Timeout(30.0),
        follow_redirects=True,
    ) as client:
        try:
            response = await client.get(url)
            response.raise_for_status()
        except (httpx.HTTPError, ValueError) as exc:
            return f"图片抓取失败（{type(exc).__name__}）。"

    data = response.content
    if not data:
        return "图片内容为空。"
    if len(data) > _MAX_BYTES:
        return f"图片超过大小限制（{_MAX_BYTES // (1024 * 1024)}MB）。"
    return BinaryContent(
        data=data,
        media_type=_media_type_from_content_type(response.headers.get("content-type")),
    )


tool = image_view
