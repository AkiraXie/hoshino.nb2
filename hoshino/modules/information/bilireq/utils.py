import asyncio
import json
from typing import Dict, List
import peewee as pw
import os
from hoshino import db_dir, Message, scheduled_job
from hoshino.util import get_bili_dynamic_screenshot, aiohttpx
from .buvid import update_buvid_params
info_url = "https://api.bilibili.com/x/space/wbi/acc/info"
dynamic_url = "https://api.bilibili.com/x/polymer/web-dynamic/v1/feed/space?host_mid={uid}&dm_cover_img_str=QU5HTEUgKEdvb2dsZSwgVnVsa2FuIDEuMy4wIChTd2lmdFNoYWRlciBEZXZpY2UgKFN1Ynplcm8pICgweDAwMDBDMFhYKSksIFN3aWZ0U2hhZGVyIGRyaXZlcilHb29nbGUgSW5jLiAoR29vZ2xlKQ"
live_url = "https://api.live.bilibili.com/room/v1/Room/get_status_info_by_uids"

headers = {
    "user-agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
        " AppleWebKit/537.36 (KHTML, like Gecko) Chrome/87.0.4280.88"
        " Safari/537.36 Edg/87.0.664.60"
    ),
}


cookies = {}
async def get_cookies() :
    if not cookies:
        cookies.update(await update_buvid_params())
    return cookies            
        


@scheduled_job("interval", hours=24, jitter=30, id="更新 b 站 cookies")
async def _():
    global cookies
    cookies = await update_buvid_params()




class Dynamic:
    def __init__(self, dynamic: dict):
        self.dynamic = dynamic
        self.type = dynamic["modules"]["module_author"]["pub_action"]
        self.id = dynamic["id_str"]
        self.url = "http://m.bilibili.com/dynamic/" + str(self.id)
        self.time = dynamic["modules"]["module_author"]["pub_ts"]
        self.uid = dynamic["modules"]["module_author"]["mid"]
        self.name = dynamic["modules"]["module_author"]["name"]

    async def get_message(self, logger) -> Message:
        msg = [self.name + self.type]
        img = await get_bili_dynamic_screenshot(self.url)
        if img:
            msg.append(str(img))
        await asyncio.sleep(0.5)
        msg.append(self.url)
        return Message("\n".join(msg))


async def get_new_dynamic(uid: int) -> Dynamic:
    url = dynamic_url.format(uid=uid)
    h = headers.copy()
    h.update({
            'origin': 'https://t.bilibili.com',
            'referer': 'https://t.bilibili.com/'
        })
    res = await aiohttpx.get(url, headers=h,cookies=await get_cookies())
    data = res.json.get("data",{})
    if not data:
        return []
    cards = data.get("items",[])
    if not cards:
        return []
    dyn = Dynamic(cards[0])
    return dyn


async def get_dynamic(uid: int,ts) -> List[Dynamic]:
    url = dynamic_url.format(uid=uid)
    h = headers.copy()
    h.update({
            'origin': 'https://t.bilibili.com',
            'referer': 'https://t.bilibili.com/'
        })
    res = await aiohttpx.get(url, headers=h,cookies=await get_cookies())
    data = res.json.get("data",{})
    if not data:
        return []
    cards = data.get("items",[])
    if not cards:
        return []
    dyn = cards[4::-1]
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
