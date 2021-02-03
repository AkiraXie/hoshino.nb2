'''
Author: AkiraXie
Date: 2021-02-04 02:33:21
LastEditors: AkiraXie
LastEditTime: 2021-02-04 03:28:06
Description: 
Github: http://github.com/AkiraXie/
'''
from hoshino import Service, Bot, Event, Message
from hoshino.typing import T_State
from .data import get_bvid, get_resp
sv = Service('bilibili')
bl = sv.on_regex(r'b23.tv/(.{6})', normal=False)


@bl.handle()
async def _(bot: Bot, state: T_State):
    url = f"https://{state['_matched']}"
    bvid = await get_bvid(url)
    res = await get_resp(bvid)
    await bl.send('检测到b站短链接或小程序，正在解析~')
    msg = []
    for k, v in res.items():
        msg.append(f'{k}: {v}')
    msg = '\n'.join(msg)
    await bl.finish(Message(msg))
