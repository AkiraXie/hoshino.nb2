from pathlib import Path
from playwright.async_api import async_playwright, Browser, Playwright, Page
from hoshino import MessageSegment
from hoshino import scheduled_job, on_startup
from nonebot.log import logger
import ssl

from hoshino.util import get_cookies

ssl._create_default_https_context = ssl._create_unverified_context
## thansks to github.com/SK-415/HarukaBot
ap: Playwright | None = None
_b: Browser | None = None
bili_mobilejs = Path(__file__).parent.joinpath("mobile.js")
weibo_script = """
document.querySelector('div.wrap')?.remove();
document.querySelector('div.ad-wrap')?.remove();
document.querySelector('div.lite-page-editor')?.remove();
"""

context_params = {
    "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.7258.5 Safari/537.36",
    "viewport": {"width": 1080, "height": 2560},
    "device_scale_factor": 2.5,
    "is_mobile": False,
}
mobile_context_params = {
    "user_agent": "Mozilla/5.0 (Linux; Android 10; M2007J3SC) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.7258.5 Mobile Safari/537.36",
    "viewport": {"width": 540, "height": 2340},
    "device_scale_factor": 3,
    "is_mobile": True,
}


@on_startup
async def get_b() -> Browser:
    global ap, _b
    if not ap or not _b:
        ap = await async_playwright().start()
        _b = await ap.chromium.launch(timeout=10000, headless=True)
    return _b


@scheduled_job("cron", hour="*/2", jitter=60, id="refresh_playwright")
async def refresh_playwright():
    global ap, _b
    if _b:
        await _b.close()
    if ap:
        await ap.stop()
    ap = await async_playwright().start()
    _b = await ap.chromium.launch(timeout=10000)


async def get_mapp_weibo_screenshot(url: str) -> MessageSegment | None:
    b: Browser = await get_b()
    d = mobile_context_params.copy()
    d["user_agent"] = (
        d["user_agent"]
        + " XWEB/13655 Flue NetType/WIFI MicroMessenger/7.0.20.1781(0x6700143B) WindowsWechat(0x63090a13) UnifiedPCWindowsWechat(0xf254032b)"
    )

    c = await b.new_context(**d)
    c.set_default_timeout(10000)
    page = None
    try:
        page: Page = await c.new_page()
        await page.goto(url)
        card = await page.wait_for_selector(".card-wrap")
        if not card:
            await page.close()
            logger.error(f"get_mapp_weibo_screenshot error: no card url: {url}")
            return None

        image = await card.screenshot()
        await page.close()
        await c.close()
        return MessageSegment.image(image)
    except Exception as e:
        if page:
            await page.close()
            await c.close()
        logger.error(f"get_mapp_weibo_screenshot error: {e} url: {url}")
        return None
    finally:
        if page:
            await page.close()
            await c.close()


async def get_weibo_screenshot_desktop(
    url: str, cookies: dict = {}
) -> MessageSegment | None:
    b: Browser = await get_b()
    c = await b.new_context(
        **context_params,
    )
    if not cookies:
        cookies = await get_cookies("weibo")
    if cookies:
        cks = []
        for k, v in cookies.items():
            if not v:
                continue
            cks.append({"name": k, "value": v, "domain": ".weibo.com", "path": "/"})
        await c.add_cookies(cks)
    c.set_default_timeout(6000)
    page = None
    try:
        page: Page = await c.new_page()
        await page.goto(url)
        selector = "article.woo-panel-main"
        element = None
        try:
            element = await page.wait_for_selector(selector, timeout=8000)
        except (TimeoutError, Exception):
            logger.error(f"get_weibo_screenshot error: no element found url: {url}  ")
            return None
        if not element:
            logger.error(f"get_weibo_screenshot error: no element found url: {url}  ")
            return None
        image = await element.screenshot()
        return MessageSegment.image(image)
    except Exception as e:
        logger.error(f"get_weibo_screenshot error: {e}")
        return None
    finally:
        if page:
            await page.close()
        if c:
            await c.close()


async def get_weibo_screenshot_mobile(
    url: str, cookies: dict = {}
) -> MessageSegment | None:
    b: Browser = await get_b()
    c = await b.new_context(
        **mobile_context_params,
    )
    if not cookies:
        cookies = await get_cookies("weibo")
    if cookies:
        cks = []
        for k, v in cookies.items():
            if not v:
                continue
            cks.append({"name": k, "value": v, "domain": ".weibo.cn", "path": "/"})
        await c.add_cookies(cks)
    c.set_default_timeout(6000)
    page = None
    try:
        page: Page = await c.new_page()
        await page.goto(url)
        try:
            await page.wait_for_selector("div.wrap", timeout=4000)
        except (TimeoutError, Exception):
            logger.warning(
                f"get_weibo_screenshot get div.wrap error: no element found. url: {url}  "
            )
            pass
        await page.add_script_tag(content=weibo_script)
        await page.wait_for_load_state("networkidle")
        selector = "div.f-weibo"
        element = None
        try:
            element = await page.wait_for_selector(selector, timeout=8000)
        except (TimeoutError, Exception):
            logger.error(f"get_weibo_screenshot error: no element found url: {url}  ")
            return None
        if not element:
            logger.error(f"get_weibo_screenshot error: no element found url: {url}  ")
            return None

        image = await element.screenshot()
        return MessageSegment.image(image)
    except Exception as e:
        logger.error(f"get_weibo_screenshot error: {e}")
        return None
    finally:
        if page:
            await page.close()
        if c:
            await c.close()


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
        await page.goto(url)
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
