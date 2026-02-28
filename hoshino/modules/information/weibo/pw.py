from pathlib import Path

from playwright.async_api import  Route
from hoshino.util.playwrights import get_ap, get_b, Page, Browser, MessageSegment, mobile_context_params,context_params
from hoshino.util import get_cookies
from nonebot.log import logger
from hoshino import config

weibo_script = """
document.querySelector('div.wrap')?.remove();
document.querySelector('div.ad-wrap')?.remove();
document.querySelector('div.lite-page-editor')?.remove();
"""

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
    c.set_default_timeout(4000)
    page = None
    try:
        page: Page = await c.new_page()
        await page.goto(url, wait_until="networkidle")
        selector = 'div[class*="body_" i]'
        element = None
        try:
            element = await page.wait_for_selector(selector, timeout=4000)
        except (TimeoutError, Exception):
            logger.error(
                f"get_weibo_screenshot timeout: no element found, url: {page.url}  "
            )
            return None
        if not element:
            logger.error(
                f"get_weibo_screenshot error: no element found, url: {page.url}  "
            )
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
        selector = "div.m-panel"
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


async def get_weibo_visitor_cookies() -> dict:
    b: Browser = await get_b()
    c = await b.new_context(
        **mobile_context_params,
    )
    times = 0
    url = 'https://m.weibo.cn'
    async def route_handler(route: Route):
        nonlocal times
        req = route.request
        rtype = req.resource_type
        rurl = req.url
        allowed_resource_types = {"document", "script", "xhr", "fetch"}

        if (rtype not in allowed_resource_types) or (times >= 2):
            await route.abort()
            return

        if rurl.startswith(url):
            times += 1

        await route.continue_()

    await c.route("**/*", route_handler)
    c.set_default_timeout(1000)
    page = None
    try:
        page: Page = await c.new_page()
        await page.goto("https://m.weibo.cn")
        await page.wait_for_load_state("networkidle")
        cookies = await c.cookies(["https://weibo.cn/"])
        ck_dict = {}
        filtered = [
            c for c in cookies
            if c.get("domain") == "weibo.cn" or str(c.get("domain", "")).endswith(".weibo.cn")
        ]
        for ck in filtered:
            ck_dict[ck["name"]] = ck["value"]
        return ck_dict
    except Exception as e:
        logger.error(f"get_weibo_visitor_cookies error: {e}")
        return {}
    finally:
        if page:
            await page.close()
        if c:
            await c.close()


async def get_weibo_cookies_from_local() -> dict:
    ap = await get_ap()
    context = await ap.chromium.launch_persistent_context(
    config.chrome_path,
    headless=True,
    channel="chrome",
    )
    page = None
    try:
        page: Page = await context.new_page()
        await page.goto("https://weibo.com")
        await page.wait_for_load_state("networkidle")
        cookies = await context.cookies()
        ck_dict = {}
        for ck in cookies:
            ck_dict[ck["name"]] = ck["value"]
        if ck_dict:
            logger.info(f"get_weibo_cookies_from_local success: got {len(ck_dict)} cookies")
        return ck_dict
    except Exception as e:
        logger.error(f"get_weibo_cookies_from_local error: {e}")
        return {}
    finally:
        if page:
            await page.close()
        if context:
            await context.close()