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

