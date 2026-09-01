"""web/browser_use：Playwright 浏览网页 → 截图 → 返回 BinaryContent。

需要看网页内容（而 web_fetch 的纯文本不够、需要"看到"页面布局/截图/渲染结果）
时使用：用仓库既有 Playwright 设施（``hoshino/util/playwrights.py``）打开页面、
等渲染完成后整页截图，返回图片给当前模型直接看。

安全：只允许 http/https、拒绝私有/回环/保留地址（同 image_view/web_fetch）；
整体浏览器操作有墙钟超时；截图超限拒绝；页面用完即关。
"""

from __future__ import annotations

import asyncio
import contextlib
from urllib.parse import urlparse

from pydantic_ai import BinaryContent, RunContext

from ... import provider
from ...deps import AgentDeps
from .net import is_private_host

_ALLOWED_SCHEMES = ("http", "https")
_MAX_SHOT_BYTES = 15 * 1024 * 1024
_BROWSER_TIMEOUT_SECONDS = 45.0
_VIEWPORT = {"width": 1280, "height": 900}


async def browse_page_screenshot(
    url: str,
    *,
    fetch_proxy: str | None = None,
) -> BinaryContent | str:
    """Playwright 打开网页 → 截图 → BinaryContent（供 browser_use 工具复用）。

    校验协议/SSRF → 截图。失败返回错误提示字符串。
    """
    parsed = urlparse(url)
    if parsed.scheme not in _ALLOWED_SCHEMES or not parsed.hostname:
        return "仅支持 http/https 网页 URL。"
    if await is_private_host(parsed.hostname):
        return "拒绝访问私有/内网地址。"

    png = await _screenshot(url, proxy=fetch_proxy)
    if isinstance(png, str):
        return png
    return BinaryContent(data=png, media_type="image/png")


async def browser_use(
    ctx: RunContext[AgentDeps],
    url: str,
    prompt: str = "这是网页截图，请描述页面主要内容与关键文字。",
):
    """用 Playwright 打开网页并截图，返回图片内容供当前模型直接看。

    - 用于需要"看"网页（布局/图表/渲染结果）的场景；
    - 禁止访问私有/内网地址；
    - ``prompt`` 保留参数兼容旧调用，实际由模型自行理解截图。
    """
    del prompt  # 原生多模态：截图直接回传，不再做描述子请求
    parsed = urlparse(url)
    if parsed.scheme not in _ALLOWED_SCHEMES or not parsed.hostname:
        return "仅支持 http/https 网页 URL。"
    if await is_private_host(parsed.hostname):
        return "拒绝访问私有/内网地址。"

    return await browse_page_screenshot(
        url,
        fetch_proxy=provider.resolve_tool_proxy(
            ctx.deps.config.proxy, tool_use_proxy=ctx.deps.config.tool_use_proxy
        ),
    )


async def _screenshot(url: str, *, proxy: str | None) -> bytes | str:
    """Playwright 打开页面并返回 PNG 字节；失败返回错误提示字符串。

    ``proxy``：页面抓取代理（可选）。Chromium 上下文级代理仅在显式传入时生效，
    默认直连（Playwright 不读取系统代理）。
    """
    from hoshino.util import playwrights

    try:
        browser = await asyncio.wait_for(playwrights.get_b(), timeout=20.0)
    except Exception as exc:
        return f"浏览器不可用（{type(exc).__name__}）。"

    context = None
    try:
        context = await asyncio.wait_for(
            browser.new_context(
                viewport=_VIEWPORT,
                proxy={"server": proxy} if proxy else None,
            ),
            timeout=_BROWSER_TIMEOUT_SECONDS,
        )
        page = await asyncio.wait_for(
            context.new_page(),
            timeout=_BROWSER_TIMEOUT_SECONDS,
        )
        await asyncio.wait_for(
            page.goto(url, wait_until="domcontentloaded", timeout=30_000),
            timeout=_BROWSER_TIMEOUT_SECONDS,
        )
        png = await asyncio.wait_for(
            page.screenshot(type="png", full_page=False),
            timeout=_BROWSER_TIMEOUT_SECONDS,
        )
    except TimeoutError:
        return "网页加载超时。"
    except Exception as exc:
        return f"网页访问失败（{type(exc).__name__}）。"
    finally:
        if context is not None:
            # 关闭 context 会连带关闭页面；失败交由浏览器进程清理，不影响截图结果。
            with contextlib.suppress(Exception):
                await context.close()

    if not png:
        return "网页截图为空。"
    if len(png) > _MAX_SHOT_BYTES:
        return f"截图超过大小限制（{_MAX_SHOT_BYTES // (1024 * 1024)}MB）。"
    return png


tool = browser_use
