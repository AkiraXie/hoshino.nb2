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


async def get_mapp_weibo_screenshot(url: str) -> MessageSegment:
    b: Browser = await get_b()
    c = await b.new_context(
        user_agent=(
            "Mozilla/5.0 (Linux; Android 10; RMX1911) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/100.0.4896.127 Mobile Safari/537.36"
        ),
        device_scale_factor=2,
    )
    page = None
    try:
        page: Page = await c.new_page()
        await page.goto(url, wait_until="networkidle")
        card = await page.query_selector(".card-wrap")
        if not card:
            await page.close()
            return None
        clip = await card.bounding_box()
        if not clip:
            await page.close()
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
        logger.error(f"get_weibo_screenshot error: {e}")
        return None
    finally:
        if page:
            await page.close()
            await c.close()


async def get_weibo_screenshot(mid: str, cookies: dict = {}) -> MessageSegment:
    url = f"https://m.weibo.cn/detail/{mid}"
    b: Browser = await get_b()
    c = await b.new_context(
        user_agent=(
            "Mozilla/5.0 (Linux; Android 10; RMX1911) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/100.0.4896.127 Mobile Safari/537.36"
        ),
        viewport={"width": 480, "height": 800},
        device_scale_factor=2,
    )
    if not cookies:
        cookies = get_cookies("weibo")
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
        await page.goto(url, wait_until="networkidle")
        await page.add_script_tag(
            content="""
    document.querySelector('.wrap')?.remove();
"""
        )
        await page.wait_for_load_state(state="networkidle")
        card = await page.query_selector(".f-weibo")
        if not card:
            await page.close()
            return None
        clip = await card.bounding_box()
        if not clip:
            await page.close()
            return None

        image = await page.screenshot(
            clip=clip, full_page=True, type="jpeg", quality=98
        )
        await page.close()
        await c.close()
        return MessageSegment.image(image)
    except Exception as e:
        if page:
            await page.close()
            await c.close()
        logger.error(f"get_weibo_screenshot error: {e}")
        return None
    finally:
        if page:
            await page.close()
            await c.close()


async def get_bili_dynamic_screenshot(url: str, cookies={}) -> MessageSegment:
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
        cookies = get_cookies("bilibili")
    cks = []
    for k, v in cookies.items():
        if not v:
            continue
        cks.append({"name": k, "value": v, "domain": ".bilibili.com", "path": "/"})
    await c.add_cookies(cks)
    page = None
    try:
        # 电脑端
        # page = await browser.new_page()
        # await page.goto(url, wait_until="networkidle", timeout=10000)
        # await page.set_viewport_size({"width": 2560, "height": 1080})
        # card = await page.query_selector(".card")
        # assert card
        # clip = await card.bounding_box()
        # assert clip
        # bar = await page.query_selector(".bili-dyn-action__icon")
        # assert bar
        # bar_bound = await bar.bounding_box()
        # assert bar_bound
        # clip["height"] = bar_bound["y"] - clip["y"]

        # 移动端
        page: Page = await c.new_page()
        await page.goto(url, wait_until="networkidle")
        if page.url == "https://m.bilibili.com/404":
            await page.close()
            return None
        await page.wait_for_load_state(state="domcontentloaded")
        await page.add_script_tag(path=mobilejs)
        await page.wait_for_function("getMobileStyle()")
        await page.wait_for_load_state("networkidle")
        await page.wait_for_load_state("domcontentloaded")
        card = await page.query_selector(
            ".opus-modules" if "opus" in page.url else ".dyn-card"
        )
        if not card:
            await page.close()
            return None
        clip = await card.bounding_box()
        if not clip:
            await page.close()
            return None

        image = await page.screenshot(
            clip=clip, full_page=True, type="jpeg", quality=98
        )
        await page.close()
        await c.close()
        return MessageSegment.image(image)
    except Exception as e:
        if page:
            await page.close()
            await c.close()
        logger.error(f"get_bili_dynamic_screenshot error: {e}")
        return None
    finally:
        if page:
            await page.close()
        await c.close()
