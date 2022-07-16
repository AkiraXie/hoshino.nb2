from hoshino.typing import Optional
from playwright.async_api import async_playwright, Browser,Playwright
from hoshino import MessageSegment
## thansks to github.com/SK-415/HarukaBot
_browser: Optional[Browser] = None
ap: Optional[Playwright] = None

async def get_browser() -> Browser:
    global _browser,ap
    if not ap or not _browser or not _browser.is_connected():
        ap = await async_playwright().start()
        _browser = await ap.chromium.launch()   
    return _browser


async def get_bili_dynamic_screenshot(url: str) -> MessageSegment:
    browser: Browser = await get_browser()
    ctx = await browser.new_context(
    device_scale_factor=2,
    # 移动端
    user_agent=(
        "Mozilla/5.0 (Linux; Android 10; RMX1911) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/100.0.4896.127 Mobile Safari/537.36"
    ),
)
        
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
        page = await ctx.new_page()
        await page.set_viewport_size({"width": 360, "height": 780})
        await page.goto(url, wait_until="networkidle", timeout=10000)
        content = await page.content()
        content = content.replace(
            '<div class="dyn-header__right">'
            '<div data-pos="follow" class="dyn-header__following">'
            '<span class="dyn-header__following__icon"></span>'
            '<span class="dyn-header__following__text">关注</span></div></div>',
            "",
        )  # 去掉关注按钮

        content = content.replace(
            '<div class="dyn-card">',
            '<div class="dyn-card" '
            'style="font-family: sans-serif; overflow-wrap: break-word;">',
        )
        # 1. 字体问题：.dyn-class里font-family是PingFangSC-Regular，使用行内CSS覆盖掉它
        # 2. 换行问题：遇到太长的内容（长单词、某些长链接等）允许强制换行，防止溢出
        content = content.replace(
            '<div class="launch-app-btn dynamic-float-openapp">'
            '<div class="m-dynamic-float-openapp">'
            "<span>打开APP，查看更多精彩内容</span></div> <!----></div>",
            "",
        )  # 去掉打开APP的按钮，防止遮挡较长的动态
        await page.set_content(content)
        card = await page.query_selector(".dyn-card")
        assert card
        clip = await card.bounding_box()
        assert clip

        image = await page.screenshot(clip=clip, full_page=True)
        await page.close()
        await ctx.close()
        return MessageSegment.image(image)
    except Exception:
        if page:
            await page.close()
        await ctx.close()
        return None


async def get_pcr_shidan(name: str) -> MessageSegment:
    browser: Browser = await get_browser()
    ctx = await browser.new_context()
    page = await ctx.new_page()
    await page.goto("https://shindan.priconne-redive.jp/", timeout=100000)
    await page.fill('input[type="text"]', name)
    await page.click("button")
    await page.wait_for_load_state("networkidle", timeout=100000)
    div = await page.wait_for_selector(
        "#app > main > div > div > div", timeout=10000000
    )
    assert div
    divbound = await div.bounding_box()
    twi = await page.wait_for_selector(
        "#app > main > div > div > div > p > a > span.tweet-btn__on.s-sm-min > img",
        timeout=10000000,
    )
    assert twi
    twibound = await twi.bounding_box()
    divbound["height"] = twibound["y"] - divbound["y"]
    img = await page.screenshot(clip=divbound, full_page=True)
    await page.close()
    await ctx.close()
    return MessageSegment.image(img)

from hoshino import driver
from nonebot.log import logger
from asyncio import sleep
@driver.on_shutdown
async def _():
    try:
        await _browser.close()
        await ap.stop()
    except Exception as e:
        logger.exception(e)   
    await sleep(0.35)
    logger.info("chromium driver has closed")