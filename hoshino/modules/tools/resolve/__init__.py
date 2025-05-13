# Thanks to https://github.com/fllesser/nonebot-plugin-resolver2

import asyncio
from hoshino import Event
from hoshino.typing import T_State
from hoshino.util import send_segments
from .data import sv, get_bvid, get_resp, parse_xhs
from json import loads
import re

bl = sv.on_regex(r"b23.tv\\?/([A-Za-z0-9]{6,7})", normal=False, full_match=False)
bv = sv.on_regex(r"BV[A-Za-z0-9]{10}", normal=False, full_match=False)


async def check_bvjson(ev: Event, state: T_State) -> bool:
    for s in ev.get_message():
        if s.type == "json":
            data = loads(s.data.get("data", "{}"))
            meta = data.get("meta")
            if meta and (c := meta.get("detail_1")):
                if q := c.get("qqdocurl"):
                    state["bvurl"] = q
                    return True
    return False


bvjson = sv.on_message(rule=check_bvjson)


@bvjson
async def _(state: T_State):
    if not (url := state.get("bvurl")):
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


@xhs
async def _(event: Event):
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
