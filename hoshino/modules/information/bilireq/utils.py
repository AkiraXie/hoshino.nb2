import asyncio
import json
from typing import Dict, List
import peewee as pw
import os
from hoshino import db_dir, Message, MessageSegment
from hoshino.util import aiohttpx, get_cookies, send_to_superuser
from hoshino.util.playwrights import get_bili_dynamic_screenshot
from time import time
from functools import partial

info_url = "https://api.bilibili.com/x/space/wbi/acc/info"
dynamic_url = (
    "https://api.bilibili.com/x/polymer/web-dynamic/v1/feed/space?host_mid={uid}"
)
live_url = "https://api.live.bilibili.com/room/v1/Room/get_status_info_by_uids"

headers = {
    "user-agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
        " AppleWebKit/537.36 (KHTML, like Gecko) Chrome/87.0.4280.88"
        " Safari/537.36 Edg/87.0.664.60"
    ),
}


get_bilicookies = partial(get_cookies, "bilibili")


class Dynamic:
    def __init__(self, dynamic: dict):
        self.dynamic = dynamic
        self.type = dynamic["modules"]["module_author"]["pub_action"]
        self.id = dynamic["id_str"]
        self.url = "http://m.bilibili.com/dynamic/" + str(self.id)
        self.time = dynamic["modules"]["module_author"]["pub_ts"]
        self.uid = dynamic["modules"]["module_author"]["mid"]
        self.name = dynamic["modules"]["module_author"]["name"]
        self.pics = []
        self.text = ""
        modules = dynamic["modules"]
        if dyn := modules.get("module_dynamic"):
            if desc := dyn.get("desc"):
                if text := desc.get("text"):
                    self.text = text
            if major := dyn.get("major"):
                match major["type"]:
                    case "MAJOR_TYPE_DRAW":
                        draw = major["draw"]
                        if items := draw.get("items"):
                            for item in items:
                                if pic := item.get("src"):
                                    self.pics.append(pic)
                    case "MAJOR_TYPE_ARCHIVE":
                        archive = major["archive"]
                        if pic := archive.get("cover"):
                            self.pics.append(pic)
                        if desc := archive.get("desc"):
                            self.text = desc
                    case "MAJOR_TYPE_OPUS":
                        opus = major["opus"]
                        if pics := opus.get("pics"):
                            for pic in pics:
                                if picurl := pic.get("url"):
                                    self.pics.append(picurl)
                        if summary := opus.get("summary"):
                            if text := summary.get("text"):
                                self.text = text
                    case "MAJOR_TYPE_ARTICLE":
                        article = major["article"]
                        if pics := article.get("covers"):
                            for pic in pics:
                                self.pics.append(pic)
                        if desc := article.get("desc"):
                            self.text = desc
                    case "MAJOR_TYPE_PGC":
                        pgc = major["pgc"]
                        if pic := pgc.get("cover"):
                            self.pics.append(pic)
                        if title := pgc.get("title"):
                            self.text = title
                    case "MAJOR_TYPE_COMMON":
                        common = major["common"]
                        if pic := common.get("cover"):
                            self.pics.append(pic)
                        if desc := common.get("desc"):
                            self.text = desc
                    case _:
                        pass

    async def get_message(self) -> list[Message | MessageSegment]:
        msg = [self.name + self.type]
        imgmsg = []
        img = await get_bili_dynamic_screenshot(
            self.url, cookies=await get_bilicookies()
        )
        if img:
            msg.append(str(img))
        else:
            msg.append(self.text)
        await asyncio.sleep(0.5)
        msg.append(self.url)
        res = [Message("\n".join(msg))]
        if self.pics:
            for pic in self.pics:
                imgmsg.append(MessageSegment.image(pic))
        res.extend(Message(imgmsg))
        return res


async def get_new_dynamic(uid: int) -> Dynamic:
    url = dynamic_url.format(uid=uid)
    h = headers.copy()
    h.update({"origin": "https://t.bilibili.com", "referer": "https://t.bilibili.com/"})

    res = await aiohttpx.get(url, headers=h, cookies=await get_bilicookies())
    data = res.json.get("data", {})
    if not data:
        return None
    cards = data.get("items", [])
    if not cards:
        return None
    dyn = Dynamic(cards[0])
    return dyn


async def get_dynamic(uid: int, ts) -> List[Dynamic]:
    url = dynamic_url.format(uid=uid)
    h = headers.copy()
    h.update({"origin": "https://t.bilibili.com", "referer": "https://t.bilibili.com/"})

    res = await aiohttpx.get(url, headers=h, cookies=await get_bilicookies())
    data = res.json.get("data", {})

    if not data:
        return []
    cards = data.get("items", [])
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
        live_url,
        data=json.dumps({"uids": uids}),
        headers=headers,
        cookies=await get_bilicookies(),
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
