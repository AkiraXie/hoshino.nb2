from playwright.async_api import Route

from hoshino.util.playwrights import (
    get_b,
    Page,
    Browser,
    MessageSegment,
    mobile_context_params,
    bili_mobilejs,
)
from hoshino.util import get_cookies
from nonebot.log import logger


async def get_bili_dynamic_screenshot(url: str, cookies={}) -> MessageSegment | None:
    b: Browser = await get_b()
    c = await b.new_context(**mobile_context_params)
    if not cookies:
        cookies = await get_cookies("bilibili")
    cks = []
    for k, v in cookies.items():
        if not v:
            continue
        cks.append({"name": k, "value": v, "domain": ".bilibili.com", "path": "/"})
    await c.add_cookies(cks)
    page = None
    c.set_default_timeout(10000)
    try:
        page: Page = await c.new_page()
        await page.goto(url, wait_until="networkidle")
        if page.url.startswith("https://m.bilibili.com/404"):
            return None
        await page.add_script_tag(path=bili_mobilejs)
        await page.wait_for_function("getMobileStyle()")
        await page.wait_for_load_state(timeout=8000)
        element = await page.wait_for_selector(
            ".opus-modules" if "opus" in page.url else ".dyn-card", timeout=8000
        )
        if not element:
            logger.error(
                f"get_bili_dynamic_screenshot error: no element found url: {url}  "
            )
            return None
        image = await element.screenshot()

        return MessageSegment.image(image)
    except Exception as e:
        logger.error(f"get_bili_dynamic_screenshot error: {e} url: {url}")
        return None
    finally:
        if page:
            await page.close()
        if c:
            await c.close()
