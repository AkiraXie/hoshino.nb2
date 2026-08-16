"""web/browser_use：Playwright 浏览网页 → 截图 → vision 模型识别 → 文字描述。

需要看网页内容（而 web_fetch 的纯文本不够、需要"看到"页面布局/截图/渲染结果）
时使用：用仓库既有 Playwright 设施（``hoshino/util/playwrights.py``）打开页面、
等渲染完成后整页截图，再把截图交给 provider 的 vision 模型描述，返回文字给调用
（默认 text）模型。text 模型不需要自己具备视觉能力。

安全：只允许 http/https、拒绝私有/回环/保留地址（同 image_view/web_fetch）；
整体浏览器操作有墙钟超时；截图超限拒绝；页面用完即关。
"""

from __future__ import annotations

import asyncio
import contextlib
from urllib.parse import urlparse

from pydantic_ai import BinaryContent, RunContext

from ... import provider, vision
from ...deps import AgentDeps
from .net import is_private_host

_ALLOWED_SCHEMES = ("http", "https")
_MAX_SHOT_BYTES = 15 * 1024 * 1024
_BROWSER_TIMEOUT_SECONDS = 45.0
_VIEWPORT = {"width": 1280, "height": 900}


async def browse_page_description(
    url: str,
    *,
    proxy: str | None,
    record,
    vision_model: str,
    prompt: str = "这是网页截图，请描述页面主要内容与关键文字。",
) -> str:
    """Playwright 打开网页 → 截图 → vision 描述（供 browser_use 工具与 zssm 复用）。

    校验协议/SSRF → 截图 → vision.describe_images。失败返回错误提示字符串。
    """
    parsed = urlparse(url)
    if parsed.scheme not in _ALLOWED_SCHEMES or not parsed.hostname:
        return "仅支持 http/https 网页 URL。"
    if await is_private_host(parsed.hostname):
        return "拒绝访问私有/内网地址。"

    png = await _screenshot(url)
    if isinstance(png, str):
        return png  # 错误提示
    content = [BinaryContent(data=png, media_type="image/png")]
    try:
        description = await vision.describe_images(
            record,
            vision_model,
            content,
            proxy=proxy,
            prompt=f"网页 {url}\n{prompt}",
        )
    except Exception as exc:
        return f"网页识别失败（{type(exc).__name__}）。"
    return description or "（网页截图暂无可识别内容）"


async def browser_use(
    ctx: RunContext[AgentDeps],
    url: str,
    prompt: str = "这是网页截图，请描述页面主要内容与关键文字。",
):
    """用 Playwright 打开网页并截图，交给 vision 模型识别，返回文字描述。

    - 用于需要"看"网页（布局/图表/渲染结果）的场景；
    - 禁止访问私有/内网地址；当前 provider 未配置 vision 模型时返回提示。
    """
    parsed = urlparse(url)
    if parsed.scheme not in _ALLOWED_SCHEMES or not parsed.hostname:
        return "仅支持 http/https 网页 URL。"
    if await is_private_host(parsed.hostname):
        return "拒绝访问私有/内网地址。"

    record, vision_model = vision.resolve_vision_model(ctx)
    if record is None:
        return "provider 配置异常。"
    if not vision_model:
        return "当前 provider 未配置 vision 模型，无法识别网页截图。"
    return await browse_page_description(
        url,
        proxy=provider.resolve_effective_proxy(record, ctx.deps.config.proxy),
        record=record,
        vision_model=vision_model,
        prompt=prompt,
    )


async def _screenshot(url: str) -> bytes | str:
    """Playwright 打开页面并返回 PNG 字节；失败返回错误提示字符串。"""
    from hoshino.util import playwrights

    try:
        browser = await asyncio.wait_for(playwrights.get_b(), timeout=20.0)
    except Exception as exc:
        return f"浏览器不可用（{type(exc).__name__}）。"

    page = None
    try:
        page = await asyncio.wait_for(
            browser.new_page(viewport=_VIEWPORT),
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
        if page is not None:
            # 关闭失败交由浏览器进程清理，不影响截图结果返回。
            with contextlib.suppress(Exception):
                await page.close()

    if not png:
        return "网页截图为空。"
    if len(png) > _MAX_SHOT_BYTES:
        return f"截图超过大小限制（{_MAX_SHOT_BYTES // (1024 * 1024)}MB）。"
    return png


tool = browser_use
