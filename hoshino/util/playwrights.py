'''
Author: AkiraXie
Date: 2022-01-06 22:13:32
LastEditors: AkiraXie
LastEditTime: 2022-02-16 17:08:54
Description: 
Github: http://github.com/AkiraXie/
'''
from hoshino.typing import Optional
from playwright.async_api import async_playwright,Browser
from hoshino import MessageSegment
_browser:Optional[Browser] = None
async def get_browser() -> Browser:
    global _browser
    if not _browser or not _browser.is_connected():
        ap = await  async_playwright().start()
        _browser = await ap.chromium.launch()
    return _browser


async def get_bili_dynamic_screenshot(url:str) -> MessageSegment:
    browser : Browser =await get_browser()
    ctx = await browser.new_context(viewport={"width": 2560, "height": 1080},device_scale_factor=2)
    page = await ctx.new_page()
    await page.goto(url, wait_until='networkidle',timeout=15000)
    card = await page.wait_for_selector(".card")
    assert card
    clip = await card.bounding_box()
    bar = await page.wait_for_selector(".text-bar")
    assert bar
    bar_bound = await bar.bounding_box()
    clip['height'] = bar_bound['y'] - clip['y']
    image = await page.screenshot(clip=clip,full_page=True)
    await page.close()
    await ctx.close()
    return MessageSegment.image(image)


async def get_pcr_shidan(name:str) ->MessageSegment:
    browser : Browser =await get_browser()
    ctx = await browser.new_context()
    page = await ctx.new_page()
    await page.goto("https://shindan.priconne-redive.jp/",timeout=100000)
    await page.fill("input[type=\"text\"]", name)
    await page.click("button")
    await page.wait_for_load_state("networkidle",timeout=100000)
    div = await page.wait_for_selector("#app > main > div > div > div",timeout=10000000)
    assert div
    divbound = await div.bounding_box()
    twi = await page.wait_for_selector("#app > main > div > div > div > p > a > span.tweet-btn__on.s-sm-min > img",timeout=10000000)
    assert twi
    twibound = await twi.bounding_box()
    divbound["height"] = twibound['y']-divbound['y']
    img = await  page.screenshot(clip=divbound,full_page=True)
    await page.close()
    await ctx.close()
    return MessageSegment.image(img)