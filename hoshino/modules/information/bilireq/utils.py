import asyncio
import json
from typing import Dict, List
import peewee as pw
import os
from hoshino import db_dir, Message
from hoshino.util import get_bili_dynamic_screenshot, aiohttpx

info_url = 'https://api.bilibili.com/x/space/acc/info?mid={uid}'
dynamic_url = 'https://api.vc.bilibili.com/dynamic_svr/v1/dynamic_svr/space_history?host_uid={uid}&offset_dynamic_id=0&need_top=0'
live_url = 'https://api.live.bilibili.com/room/v1/Room/get_status_info_by_uids'
headers = {
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)\
             AppleWebKit/537.36 (KHTML, like Gecko) Chrome/87.0.4280.88\
              Safari/537.36 Edg/87.0.664.60',
    'Referer': 'https://www.bilibili.com/'
}


class Dynamic():

    def __init__(self, dynamic: dict):
        self.dynamic = dynamic
        self.type = dynamic['desc']['type']
        self.id = dynamic['desc']['dynamic_id']
        self.url = "https://t.bilibili.com/" + str(self.id)
        self.time = dynamic['desc']['timestamp']
        self.uid = dynamic['desc']['user_profile']['info']['uid']
        self.name = dynamic['desc']['user_profile']['info'].get('uname')

    async def get_message(self, logger) -> Message:
        type_msg = {
            0: "发布了新动态",
            1: "转发了一条动态",
            8: "发布了新投稿",
            16: "发布了短视频",
            64: "发布了新专栏",
            256: "发布了新音频"
        }
        msg = [self.name+type_msg.get(self.type, type_msg[0])]
        for i in range(3):
            try:
                img = await get_bili_dynamic_screenshot(self.url)
                msg.append(str(img))
                break
            except:
                logger.exception("获取动态截图失败")
            await asyncio.sleep(0.2)
        msg.append(self.url)
        return Message("\n".join(msg))


async def get_new_dynamic(uid: int) -> Dynamic:
    url = dynamic_url.format(uid=uid)
    res = await aiohttpx.get(url, headers=headers)
    data = res.json['data']
    dyn = data.get('cards')[0]
    dyn = Dynamic(dyn)
    return dyn


async def get_dynamic(uid: int, ts: int) -> List[Dynamic]:
    url = dynamic_url.format(uid=uid)
    res = await aiohttpx.get(url, headers=headers)
    data = res.json['data']
    dyn = data.get('cards')[4::-1]
    dyns = list(map(Dynamic, dyn))
    dyns = [d for d in dyns if d.time > ts.timestamp()]
    return dyns


async def get_user_name(uid: int):
    url = info_url.format(uid=uid)
    res = await aiohttpx.get(url, headers=headers)
    data = res.json['data']
    return data['name']


async def get_live_status(uids: List[int]) -> Dict[str, Dict]:
    res = await aiohttpx.post(live_url, data=json.dumps({"uids": uids}), headers=headers)
    data: Dict[str, Dict] = res.json['data']
    return data


db_path = os.path.join(db_dir, 'bilidata.db')
db = pw.SqliteDatabase(db_path)


class DynamicDB(pw.Model):
    uid = pw.IntegerField()
    group = pw.IntegerField()
    time = pw.TimestampField()
    name = pw.TextField()

    class Meta:
        database = db
        primary_key = pw.CompositeKey('uid', 'group')


class LiveDB(pw.Model):
    uid = pw.IntegerField()
    group = pw.IntegerField()
    name = pw.TextField()
    class Meta:
        database = db
        primary_key = pw.CompositeKey('uid', 'group')


if not os.path.exists(db_path):
    db.connect()
    db.create_tables([DynamicDB,LiveDB])
    db.close()
