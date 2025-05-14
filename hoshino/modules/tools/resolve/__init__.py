# Thanks to https://github.com/fllesser/nonebot-plugin-resolver2
## TODO: suppport weibo
import asyncio
from hoshino import Event
from hoshino.typing import T_State
from hoshino.util import send_segments
from .data import sv, get_bvid, get_bv_resp, parse_xhs
from json import loads
import re


urlmaps = {
    "detail_1": "qqdocurl",
    "news": "jumpUrl",
    "music": "jumpUrl",
}
replacements = {"&#44;": ",", "\\": "", "&amp;": "&"}

regexs = {
    "b23": r"b23.tv\\?/([A-Za-z0-9]{6,7})",
    "bv": r"BV[A-Za-z0-9]{10}",
    "xhs": r"(http:|https:)\/\/(xhslink|(www\.)xiaohongshu).com\/[A-Za-z\d._?%&+\-=\/#@]*",
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
    for name, regex in regexs.items():
        if matched := re.search(regex, url):
            state["__url_name"] = name
            state["__url"] = url
            state["__url_matched"] = matched
            return True
    return False


m = sv.on_message(rule=check_json_or_text, log=True)


@m
async def _(state: T_State):
    if not (url := state.get("__url")):
        return
    if not (name := state.get("__url_name")):
        return
    if not (matched := state.get("__url_matched")):
        return
    name = name.lower()
    bvid = None
    xhs_url = None
    if name == "b23":
        bvurl = f"https://b23.tv/{matched.group(1)}"
        bvid = await get_bvid(bvurl)
    elif name == "bv":
        bvid = matched.group(0)
    elif name == "xhs":
        xhs_url = matched.group(0)
    if not bvid and not xhs_url:
        return
    if bvid:
        msg = await get_bv_resp(bvid)
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
