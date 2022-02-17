"""
Author: AkiraXie
Date: 2021-02-04 02:33:21
LastEditors: AkiraXie
LastEditTime: 2022-02-16 22:32:20
Description: 
Github: http://github.com/AkiraXie/
"""
from hoshino import Service, Bot, Event, Message
from hoshino.typing import T_State
from .data import get_bvid, get_resp

sv = Service("bilibili")
bl = sv.on_regex(r"b23.tv\\?/([A-Za-z0-9]{6,7})", normal=False, full_match=False)
bv = sv.on_regex(r"BV[A-Za-z0-9]{10}", normal=False, full_match=False)


@bl
async def _(state: T_State):
    url = f"https://b23.tv/{state['match'].group(1)}"
    bvid = await get_bvid(url)
    if not bvid:
        await bl.finish()
    res = await get_resp(bvid)
    if not res:
        await bl.finish()
    await bl.send("检测到b站视频短链接或小程序，正在解析~")
    msg = []
    for k, v in res.items():
        msg.append(f"{k}: {v}")
    msg = "\n".join(msg)
    await bl.finish(Message(msg))


@bv
async def _(state: T_State):
    bvid = state["_matched"]
    res = await get_resp(bvid)
    if not res:
        await bv.finish()
    await bv.send("检测到b站视频，正在解析~")
    msg = []
    for k, v in res.items():
        msg.append(f"{k}: {v}")
    msg = "\n".join(msg)
    await bv.finish(Message(msg))
