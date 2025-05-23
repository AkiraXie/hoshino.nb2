from pathlib import Path
from hoshino.typing import Optional
from playwright.async_api import async_playwright, Browser, Playwright, Page
from hoshino import MessageSegment
from hoshino import scheduled_job
from nonebot.log import logger
import ssl

from hoshino.util import get_cookies

ssl._create_default_https_context = ssl._create_unverified_context
## thansks to github.com/SK-415/HarukaBot
ap: Optional[Playwright] = None
_b: Optional[Browser] = None
mobilejs = Path(__file__).parent.joinpath("mobile.js")


async def get_b() -> Browser:
    global ap, _b
    if not ap or not _b:
        ap = await async_playwright().start()
        _b = await ap.chromium.launch(timeout=10000)
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
    c = await b.new_context(
        user_agent=(
            "Mozilla/5.0 (Linux; Android 10; RMX1911) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/100.0.4896.127 Mobile Safari/537.36 "
            "XWEB/13655 Flue "
            "NetType/WIFI "
            "MicroMessenger/7.0.20.1781(0x6700143B) WindowsWechat(0x63090a13) UnifiedPCWindowsWechat(0xf254032b)"
        ),
        device_scale_factor=2,
    )
    page = None
    try:
        page: Page = await c.new_page()
        await page.goto(url, wait_until="domcontentloaded")
        card = await page.wait_for_selector(".card-wrap")
        if not card:
            await page.close()
            logger.error("get_mapp_weibo_screenshot error: no card")
            return None
        clip = await card.bounding_box()
        if not clip:
            await page.close()
            logger.error("get_mapp_weibo_screenshot error: no clip")
            return None

        image = await page.screenshot(
            clip=clip, full_page=True, type="jpeg", quality=100
        )
        await page.close()
        await c.close()
        return MessageSegment.image(image)
    except Exception as e:
        if page:
            await page.close()
            await c.close()
        logger.error(f"get_mapp_weibo_screenshot error: {e}")
        return None
    finally:
        if page:
            await page.close()
            await c.close()


async def get_weibo_screenshot(url: str, cookies: dict = {}) -> MessageSegment | None:
    b: Browser = await get_b()
    c = await b.new_context(
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/136.0.0.0 Safari/537.36"
        ),
        device_scale_factor=1.5,
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
    page = None
    try:
        page: Page = await c.new_page()
        await page.goto(url, wait_until="domcontentloaded")
        # Try different selectors for the element
        selectors = [".feed_body", ".Feed_body_3R0r0", "article.woo-panel-main"]
        element = None
        for selector in selectors:
            try:
                element = await page.wait_for_selector(selector, timeout=4000)
                if element:
                    break
            except (TimeoutError, Exception):
                continue
        if not element:
            logger.error("get_weibo_screenshot error: no element found")
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
    c = await b.new_context(
        user_agent=(
            "Mozilla/5.0 (Linux; Android 10; RMX1911) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/100.0.4896.127 Mobile Safari/537.36"
        ),
        viewport={"width": 460, "height": 780},
        device_scale_factor=2,
    )
    if not cookies:
        cookies = await get_cookies("bilibili")
    cks = []
    for k, v in cookies.items():
        if k == "SESSDATA":
            cks.append({"name": k, "value": v, "domain": ".bilibili.com", "path": "/"})
            break
        else:
            continue
    await c.add_cookies(cks)
    page = None
    try:
        page: Page = await c.new_page()
        await page.goto(url, wait_until="domcontentloaded")
        if page.url.startswith("https://m.bilibili.com/404"):
            return None
        await page.add_script_tag(path=mobilejs)
        await page.wait_for_function("getMobileStyle()")
        await page.wait_for_load_state("domcontentloaded")
        element = await page.wait_for_selector(
            ".opus-modules" if "opus" in page.url else ".dyn-card"
        )
        if not element:
            logger.error("get_bili_dynamic_screenshot error: no element found")
            return None
        image = await element.screenshot()

        return MessageSegment.image(image)
    except Exception as e:
        logger.error(f"get_bili_dynamic_screenshot error: {e}")
        return None
    finally:
        if page:
            await page.close()
        if c:
            await c.close()
