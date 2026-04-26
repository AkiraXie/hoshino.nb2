# Thanks to https://github.com/fllesser/nonebot-plugin-resolver2
from hoshino import Event, Bot
from nonebot.typing import T_State
from .bilidata import (
    resolve_bilibili,
)
from .sv import sv
from .xiaohongshu import resolve_xiaohongshu
from json import loads
import re
from .weibo import resolve_weibo
from .douyin import resolve_douyin

urlmaps = {
    "detail_1": "qqdocurl",
    "news": "jumpUrl",
    "music": "jumpUrl",
}
replacements = {"&#44;": ",", "\\": "", "&amp;": "&"}

regexs = {
    "b23": re.compile(r"(http:|https:)\/\/b23.tv\\?/([A-Za-z0-9]+)"),
    "bilibilicn": re.compile(r"(http:|https:)\/\/bilibili2233.cn\\?/([A-Za-z0-9]+)"),
    "bv": re.compile(r"BV[A-Za-z0-9]{10}"),
    "av": re.compile(r"av(\d{6,})"),
    "xhs": re.compile(
        r"(http:|https:)\/\/(xhslink|(www\.)xiaohongshu).com\/[A-Za-z\d._?%&+\-=\/#@]*"
    ),
    "weibo": re.compile(r"(http:|https:)\/\/weibo\.com\/(\d+)\/(\w+)"),
    "mweibo": re.compile(r"(http:|https:)\/\/m\.weibo\.cn\/(detail|status)\/(\w+)"),
    "mappweibo": re.compile(r"(http:|https:)\/\/mapp\.api\.weibo\.cn\/fx\/(\w+)\.html"),
    "bilibilidyn": re.compile(
        r"(http:|https:)\/\/(t|www|m)?\.?bilibili\.com\/(opus\/|dynamic\/)?(\d+)"
    ),
    "vdouyin": re.compile(r"https://v\.douyin\.com/[a-zA-Z0-9_\-]+"),
    "douyin": re.compile(
        r"https://www\.(?:douyin|iesdouyin)\.com/(?:video|note|share/(?:video|note|slides))/[0-9]+"
    ),
}


async def check_json_or_text(ev: Event, state: T_State) -> bool:
    url = None
    jsonFlag = False
    for s in ev.get_message():
        if s.type == "json":
            data = loads(s.data.get("data", "{}"))
            meta = data.get("meta")
            if meta:
                for k, v in urlmaps.items():
                    if k in meta:
                        url = meta[k].get(v)
                        if url:
                            for old, new in replacements.items():
                                url = url.replace(old, new)
                            jsonFlag = True
                            break
    url = ev.get_plaintext() if not jsonFlag else url
    if not url:
        return False
    url = url.strip()
    for name, regex in regexs.items():
        if matched := regex.search(url):
            state["__url_name"] = name
            state["__url"] = matched.group(0)
            state["__url_matched"] = matched
            sv.logger.info(f"Matched URL: {state['__url']}")
            return True
    return False


m = sv.on_message(rule=check_json_or_text, log=True, priority=3, block=False)


@m
async def parse_handler(bot: Bot, state: T_State, ev: Event):
    if not (name := state.get("__url_name")):
        return
    if not (matched := state.get("__url_matched")):
        return
    if not (url := state.get("__url")):
        return
    name = name.lower()
    match name:
        case "b23" | "bilibilicn" | "bv" | "av" | "bilibilidyn":
            if await resolve_bilibili(name, url, matched):
                await m.finish()
            return
        case "xhs":
            if await resolve_xiaohongshu(bot, ev, url):
                await m.finish()
            return
        case "weibo" | "mweibo":
            _, _, bid = matched.groups()
            if await resolve_weibo(name, url, bid=bid):
                await m.finish()
            return
        case "mappweibo":
            if await resolve_weibo(name, url):
                await m.finish()
            return
        case "vdouyin" | "douyin":
            if await resolve_douyin(name, url):
                await m.finish()
            return
        case _:
            return
