'''
Author: AkiraXie
Date: 2021-02-04 02:18:33
LastEditors: AkiraXie
LastEditTime: 2021-02-04 03:00:33
Description: 
Github: http://github.com/AkiraXie/
'''
from hoshino import MessageSegment
from hoshino.util import aiohttpx
import re
headers = {
    "User-Agent": "Mozilla/5.0",
    "Referer": "https://www.bilibili.com/",
}



async def get_bvid(url: str) -> str:
    resp = await aiohttpx.head(url, allow_redirects=False)
    loc = resp.headers['Location']
    pat = re.compile(r'https://www.bilibili.com/video/(.{12})')    
    if mat:=pat.match(loc):
        return mat.group(1)
    else:
        return None


async def get_resp(bvid: str):
    url = 'https://api.bilibili.com/x/web-interface/view?bvid=' + bvid
    try:
        resp = await aiohttpx.get(url, headers=headers)
    except:
        return None
    js = resp.json
    data = js.get("data")
    if not data:
        return None
    oj = dict()
    oj['封面'] = MessageSegment.image(data['pic'])
    oj['av号'] = f'av{data.get("aid")}'
    oj['标题'] = data['title']
    oj['简介'] = data['desc']
    oj['UP主'] = data['owner']['name']
    oj['UP主空间'] = f"https://space.bilibili.com/{data['owner']['mid']}"
    oj['链接'] = f'https://bilibili.com/video/{bvid}'
    return oj
