import asyncio
import json
from typing import Dict, List
import peewee as pw
from aiohttp import ClientSession
import os
from hoshino import db_dir, Message
from hoshino.util import get_bili_dynamic_screenshot, aiohttpx
from functools import reduce
# from .render import get_dynamic_img
import time
import urllib.parse
from hashlib import md5
info_url = "https://api.bilibili.com/x/space/wbi/acc/info"
dynamic_url = "https://api.vc.bilibili.com/dynamic_svr/v1/dynamic_svr/space_history?host_uid={uid}&offset_dynamic_id=0&need_top=0"
live_url = "https://api.live.bilibili.com/room/v1/Room/get_status_info_by_uids"
headers = {
    "user-agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
        " AppleWebKit/537.36 (KHTML, like Gecko) Chrome/87.0.4280.88"
        " Safari/537.36 Edg/87.0.664.60"
    ),
    "Referer": "https://www.bilibili.com/",
}
cookies = {}
async def get_cookies() :
    if not cookies:
        async with ClientSession() as s:
            async with s.get("https://www.bilibili.com/",headers=headers) as resp:
                cookies.update(resp.cookies)
    return cookies            
        



mixinKeyEncTab = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35, 27, 43, 5, 49,
    33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13, 37, 48, 7, 16, 24, 55, 40,
    61, 26, 17, 0, 1, 60, 51, 30, 4, 22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11,
    36, 20, 34, 44, 52
]

def getMixinKey(orig: str):
    '对 imgKey 和 subKey 进行字符顺序打乱编码'
    return reduce(lambda s, i: s + orig[i], mixinKeyEncTab, '')[:32]


def encWbi(params: dict, img_key: str, sub_key: str):
    '为请求参数进行 wbi 签名'
    mixin_key = getMixinKey(img_key + sub_key)
    curr_time = round(time.time())
    params['wts'] = curr_time                                   # 添加 wts 字段
    params = dict(sorted(params.items()))                       # 按照 key 重排参数
    # 过滤 value 中的 "!'()*" 字符
    params = {
        k : ''.join(filter(lambda chr: chr not in "!'()*", str(v)))
        for k, v 
        in params.items()
    }
    query = urllib.parse.urlencode(params)                      # 序列化参数
    wbi_sign = md5((query + mixin_key).encode()).hexdigest()    # 计算 w_rid
    params['w_rid'] = wbi_sign
    params["token"] = params.get("token", "")
    params["platform"] = params.get("platform", "web")
    params["web_location"] = params.get("web_location", 1550101)
    return params


async def getWbiKeys() -> tuple[str, str]:
    '获取最新的 img_key 和 sub_key'
    resp = await aiohttpx.get('https://api.bilibili.com/x/web-interface/nav',headers=headers)
    if not resp.ok:
        raise Exception('get data from nav failed')
    json_content = resp.json
    img_url: str = json_content['data']['wbi_img']['img_url']
    sub_url: str = json_content['data']['wbi_img']['sub_url']
    img_key = img_url.rsplit('/', 1)[1].split('.')[0]
    sub_key = sub_url.rsplit('/', 1)[1].split('.')[0]
    return img_key, sub_key

async def get_wbi_params(params:dict) -> dict:
    img_key,sub_key = await getWbiKeys()
    return encWbi(params,img_key,sub_key)




class Dynamic:
    def __init__(self, dynamic: dict):
        self.dynamic = dynamic
        self.type = dynamic["desc"]["type"]
        self.id = dynamic["desc"]["dynamic_id"]
        self.url = "http://m.bilibili.com/dynamic/" + str(self.id)
        self.time = dynamic["desc"]["timestamp"]
        self.uid = dynamic["desc"]["user_profile"]["info"]["uid"]
        self.name = dynamic["desc"]["user_profile"]["info"].get("uname")

    async def get_message(self, logger) -> Message:
        type_msg = {
            0: "发布了新动态",
            1: "转发了一条动态",
            8: "发布了新投稿",
            16: "发布了短视频",
            64: "发布了新专栏",
            256: "发布了新音频",
        }
        msg = [self.name + type_msg.get(self.type, type_msg[0])]
        for _ in range(3):
            #img = await get_dynamic_img(self.id)
            img = await get_bili_dynamic_screenshot(self.url)
            if img:
                msg.append(str(img))
                break
            await asyncio.sleep(0.5)
        msg.append(self.url)
        return Message("\n".join(msg))


async def get_new_dynamic(uid: int) -> Dynamic:
    url = dynamic_url.format(uid=uid)
    res = await aiohttpx.get(url,cookies=await get_cookies(), headers=headers)
    data = res.json["data"]
    dyn = data.get("cards")[0]
    dyn = Dynamic(dyn)
    return dyn


async def get_dynamic(uid: int,ts) -> List[Dynamic]:
    url = dynamic_url.format(uid=uid)
    res = await aiohttpx.get(url,cookies=await get_cookies(), headers=headers)
    data = res.json["data"]
    if not data:
        return []
    dyn = data.get("cards",[])[4::-1]
    dyns = list(map(Dynamic, dyn))
    dyns = [d for d in dyns if d.time > ts.timestamp()]
    return dyns


async def get_user_name(uid: int):
    dyn = await get_new_dynamic(uid)
    return dyn.name


async def get_live_status(uids: List[int]) -> Dict[str, Dict]:
    res = await aiohttpx.post(
        live_url, data=json.dumps({"uids": uids}), headers=headers
    )
    data: Dict[str, Dict] = res.json["data"]
    return data


db_path = os.path.join(db_dir, "bilidata.db")
db = pw.SqliteDatabase(db_path)


class DynamicDB(pw.Model):
    uid = pw.IntegerField()
    group = pw.IntegerField()
    time = pw.TimestampField()
    name = pw.TextField()

    class Meta:
        database = db
        primary_key = pw.CompositeKey("uid", "group")


class LiveDB(pw.Model):
    uid = pw.IntegerField()
    group = pw.IntegerField()
    name = pw.TextField()

    class Meta:
        database = db
        primary_key = pw.CompositeKey("uid", "group")


if not os.path.exists(db_path):
    db.connect()
    db.create_tables([DynamicDB, LiveDB])
    db.close()
