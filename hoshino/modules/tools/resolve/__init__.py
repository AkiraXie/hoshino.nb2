# Thanks to https://github.com/fllesser/nonebot-plugin-resolver2
import asyncio
from hoshino import Event
from hoshino.typing import T_State
from hoshino.util import send_segments, get_redirect, send
from .data import (
    sv,
    get_bili_video_resp,
    parse_xhs,
    get_bvid,
    get_dynamic_from_url,
)
from json import loads
import re
from hoshino.modules.information.weibo.utils import (
    parse_mapp_weibo,
    parse_weibo_with_bid,
)

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
    url = url.strip()
    if not url:
        return False
    for name, regex in regexs.items():
        if matched := regex.search(url):
            state["__url_name"] = name
            state["__url"] = matched.group(0)
            state["__url_matched"] = matched
            return True
    return False


m = sv.on_message(rule=check_json_or_text, log=True, priority=3, block=False)


@m
async def _(state: T_State):
    if not (name := state.get("__url_name")):
        return
    if not (matched := state.get("__url_matched")):
        return
    if not (url := state.get("__url")):
        return
    name = name.lower()
    bvid = None
    burl = None
    xhs_url = None
    avid = None
    if name == "b23" or name == "bilibilicn":
        bvid = await get_bvid(url)
        if not bvid:
            burl = await get_redirect(url)
    elif name == "bv":
        bvid = matched.group(0)
    elif name == "av":
        avid = matched.group(1)
    elif name == "bilibilidyn":
        burl = url
    elif name == "xhs":
        xhs_url = url
    elif name == "weibo":
        _, _, bid = matched.groups()
        post = await parse_weibo_with_bid(bid)
        if not post:
            sv.logger.error(f"{name} parse error")
            return
        await asyncio.sleep(0.3)
        ms = await post.get_msg_with_screenshot()
        if not ms:
            return
        await send(ms[0])
        await asyncio.sleep(0.2)
        await send_segments(ms[1:])
        await m.finish()
    elif name == "mweibo":
        _, _, bid = matched.groups()
        post = await parse_weibo_with_bid(bid)
        if not post:
            sv.logger.error(f"{name} parse error")
            return
        await asyncio.sleep(0.3)
        ms = await post.get_msg_with_screenshot()
        if not ms:
            return
        await send(ms[0])
        await asyncio.sleep(0.2)
        await send_segments(ms[1:])
        await m.finish()
    elif name == "mappweibo":
        post = await parse_mapp_weibo(url)
        if not post:
            sv.logger.error(f"{name} parse error")
            return
        await asyncio.sleep(0.3)
        ms = await post.get_msg_with_screenshot()
        if not ms:
            return
        await send(ms[0])
        await asyncio.sleep(0.2)
        await send_segments(ms[1:])
        await m.finish()
    if not bvid and not xhs_url and not burl and not avid:
        return
    if bvid:
        msg = await get_bili_video_resp(bvid=bvid)
        if not msg:
            return
        await asyncio.sleep(0.3)
        await m.finish(msg)
    if avid:
        msg = await get_bili_video_resp(avid=avid)
        if not msg:
            return
        await asyncio.sleep(0.3)
        await m.finish(msg)
    if xhs_url:
        msgs = await parse_xhs(xhs_url)
        if not msgs:
            return
        await asyncio.sleep(0.3)
        await send_segments(msgs)
        await m.finish()
    if burl:
        dyn = await get_dynamic_from_url(burl)
        if not dyn:
            return
        msgs = await dyn.get_message()
        if not msgs:
            return
        await send_segments(msgs)
