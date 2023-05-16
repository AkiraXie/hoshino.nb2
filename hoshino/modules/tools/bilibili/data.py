"""
Author: AkiraXie
Date: 2021-02-04 02:18:33
LastEditors: AkiraXie
LastEditTime: 2021-02-04 03:00:33
Description: 
Github: http://github.com/AkiraXie/
"""
from hoshino import MessageSegment,Message
from hoshino.util import aiohttpx
from time import strftime,localtime
import re

headers = {
    "User-Agent": "Mozilla/5.0",
    "Referer": "https://www.bilibili.com/",
}
pat = re.compile(r"https://www.bilibili.com/video/(.{12})")

async def get_bvid(url: str) -> str:
    resp = await aiohttpx.head(url, allow_redirects=False)
    loc = resp.headers["Location"]
    if mat := pat.match(loc):
        return mat.group(1)
    else:
        return None

# 处理超过一万的数字
def handle_num(num: int) -> str:
    if num > 10000:
        s = f"{(num / 10000.0):.2f}万"
    else :
        s = str(num)   
    return s

async def get_resp(bvid: str) ->Message:
    url = "https://api.bilibili.com/x/web-interface/view?bvid=" + bvid
    try:
        resp = await aiohttpx.get(url, headers=headers)
    except:
        return None
    js = resp.json
    res = js.get("data")
    if not res:
        return None
    
    pubdate = strftime("%Y-%m-%d %H:%M:%S", localtime(res["pubdate"]))
    msg = []
    msg.append(str(MessageSegment.image(res["pic"])))
    msg.append(f"https://www.bilibili.com/video/av{res['aid']}")
    msg.append(f"标题：{res['title']}")
    msg.append(f"类型：{res['tname']} | UP：{res['owner']['name']} | 日期：{pubdate}")
    msg.append(f"播放：{handle_num(res['stat']['view'])} | 弹幕：{handle_num(res['stat']['danmaku'])} | 收藏：{handle_num(res['stat']['favorite'])}")
    return Message("\n".join(msg))
