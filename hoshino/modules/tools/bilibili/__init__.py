"""
Author: AkiraXie
Date: 2021-02-04 02:33:21
LastEditors: AkiraXie
LastEditTime: 2022-02-16 22:32:20
Description: 
Github: http://github.com/AkiraXie/
"""
import asyncio
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
    msg = await get_resp(bvid)
    if not msg:
        await bl.finish()
    await bl.send("检测到b站视频，正在解析~")
    await asyncio.sleep(0.3)
    await bl.finish(msg)


@bv
async def _(state: T_State):
    bvid = state["_matched"]
    msg = await get_resp(bvid)
    if not msg:
        await bv.finish()
    await bv.send("检测到b站视频，正在解析~")
    await asyncio.sleep(0.3)
    await bv.finish(msg)