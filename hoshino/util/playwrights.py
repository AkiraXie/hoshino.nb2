from pathlib import Path
from hoshino.typing import Optional
from playwright.async_api import async_playwright, BrowserContext,Playwright,Page
from hoshino import MessageSegment
from hoshino import R
from nonebot.log import logger

## thansks to github.com/SK-415/HarukaBot
_ctx: Optional[BrowserContext] = None
mobilejs = Path(__file__).parent.joinpath("mobile.js")
async def get_ctx() -> BrowserContext:
    user_data = R / "playwright"
    global _ctx
    if not _ctx:
        ap = await async_playwright().start()   
        _ctx = await ap.chromium.launch_persistent_context(   
        user_data_dir=user_data,
        device_scale_factor=2,
        timeout=30000,
        user_agent=(
        "Mozilla/5.0 (Linux; Android 10; RMX1911) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/100.0.4896.127 Mobile Safari/537.36"
        ),
        viewport={"width": 460, "height": 780},)
    return _ctx


async def get_bili_dynamic_screenshot(url: str) -> MessageSegment:
    ctx = await get_ctx()        
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
        page :Page = await ctx.new_page()
        await page.goto(url, wait_until="networkidle")
        if page.url == "https://m.bilibili.com/404":
            await page.close()
            return None
        await page.wait_for_load_state(state="domcontentloaded")
        await page.add_script_tag(
            path=mobilejs
        )
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

        image = await page.screenshot(clip=clip, full_page=True, type="jpeg", quality=98)
        await page.close()
        return MessageSegment.image(image)
    except Exception as e:
        if page:
            await page.close()
        logger.error(f"get_bili_dynamic_screenshot error: {e}")
        return None
    finally:
        if page:
            await page.close()


# async def get_pcr_shidan(name: str) -> MessageSegment:
#     browser: Browser = await get_browser()
#     ctx = await browser.new_context()
#     page = await ctx.new_page()
#     await page.goto("https://shindan.priconne-redive.jp/", timeout=100000)
#     await page.fill('input[type="text"]', name)
#     await page.click("button")
#     await page.wait_for_load_state("networkidle", timeout=100000)
#     div = await page.wait_for_selector(
#         "#app > main > div > div > div", timeout=10000000
#     )
#     assert div
#     divbound = await div.bounding_box()
#     twi = await page.wait_for_selector(
#         "#app > main > div > div > div > p > a > span.tweet-btn__on.s-sm-min > img",
#         timeout=10000000,
#     )
#     assert twi
#     twibound = await twi.bounding_box()
#     divbound["height"] = twibound["y"] - divbound["y"]
#     img = await page.screenshot(clip=divbound, full_page=True)
#     await page.close()
#     await ctx.close()
#     return MessageSegment.image(img)
