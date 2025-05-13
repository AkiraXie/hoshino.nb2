# Thanks to https://github.com/fllesser/nonebot-plugin-resolver2
## TODO: suppport weibo
import asyncio
from hoshino import Event
from hoshino.typing import T_State
from hoshino.util import send_segments
from .data import sv, get_bvid, get_resp, parse_xhs
from json import loads
import re

bl = sv.on_regex(r"b23.tv\\?/([A-Za-z0-9]{6,7})", normal=False, full_match=False)
bv = sv.on_regex(r"BV[A-Za-z0-9]{10}", normal=False, full_match=False)

urlmaps = {
    "detail_1": "qqdocurl",
    "news": "jumpUrl",
    "music": "jumpUrl",
}
replacements = {"&#44;": ",", "\\": "", "&amp;": "&"}


async def check_json(ev: Event, state: T_State) -> bool:
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
                            state["url"] = url
                            return True
    return False


bvjson = sv.on_message(rule=check_json)


@bvjson
async def _(state: T_State):
    if not (url := state.get("url")):
        return
    bvid = await get_bvid(url)
    if not bvid:
        return
    msg = await get_resp(bvid)
    if not msg:
        return
    await asyncio.sleep(0.3)
    await bvjson.finish(msg)


@bl
async def _(state: T_State):
    url = f"https://b23.tv/{state['match'].group(1)}"
    bvid = await get_bvid(url)
    if not bvid:
        await bl.finish()
    msg = await get_resp(bvid)
    if not msg:
        await bl.finish()
    await asyncio.sleep(0.3)
    await bl.finish(msg)


@bv
async def _(state: T_State):
    bvid = state["_matched"]
    msg = await get_resp(bvid)
    if not msg:
        await bv.finish()
    await asyncio.sleep(0.3)
    await bv.finish(msg)


xhs = sv.on_keyword(("xhslink.com", "xiaohongshu.com"))
xhsjson = sv.on_message(rule=check_json)


@xhs
async def parse_xhs_ev(event: Event):
    text = event.get_plaintext()
    pattern = (
        r"(http:|https:)\/\/(xhslink|(www\.)xiaohongshu).com\/[A-Za-z\d._?%&+\-=\/#@]*"
    )
    matched = re.search(pattern, text)
    if not matched:
        await xhs.finish()
    url = matched.group(0)
    msgs = await parse_xhs(url)
    if not msgs:
        await xhs.finish()
    await send_segments(msgs)


@xhsjson
async def parse_xhs_json(state: T_State):
    if not (url := state.get("url")):
        return
    pattern = (
        r"(http:|https:)\/\/(xhslink|(www\.)xiaohongshu).com\/[A-Za-z\d._?%&+\-=\/#@]*"
    )
    matched = re.search(pattern, url)
    if not matched:
        return
    msgs = await parse_xhs(url)
    if not msgs:
        return
    await send_segments(msgs)
