import asyncio
import base64
import json
import math
import random
from nonebot.typing import override
from sqlalchemy import (
    Float,
    Integer,
    Text,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from hoshino import (
    db_dir,
    Message,
    MessageSegment,
)
from hoshino.service import Service
from hoshino.util import (
    aiohttpx,
    get_cookies_with_ts,
)
from .pw import get_bili_dynamic_screenshot

from ..utils import Post
from typing import Sequence
from dataclasses import dataclass


sv = Service("bilireq", enable_on_default=False)
info_url = "https://api.bilibili.com/x/space/wbi/acc/info"
dynamic_url = "https://api.bilibili.com/x/polymer/web-dynamic/v1/feed/space"
live_url = "https://api.live.bilibili.com/room/v1/Room/get_status_info_by_uids"
nav_url = "https://api.bilibili.com/x/web-interface/nav"


headers = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0"
    ),
    "Referer": "https://www.bilibili.com",
}

def random_hex_str(length: int) -> str:
    result = ""
    for _ in range(length):
        result += dec2hex_upper(16 * random.random())
    return pad_string_with_zeros(result, length)

def dec2hex_upper(e: float) -> str:
    return format(math.ceil(e), 'X')


def pad_string_with_zeros(s: str, length: int) -> str:
    return s.zfill(length)

def generate_gaussian_integer(mean: float, std: float) -> int:
    TWO_PI = math.pi * 2
    u1 = random.random()
    u2 = random.random()
    z0 = math.sqrt(-2 * math.log(u1)) * math.cos(TWO_PI * u2)
    return round(z0 * std + mean)

def get_dm_img_list() -> str:
    x = max(generate_gaussian_integer(1245, 5), 0)
    y = max(generate_gaussian_integer(1285, 5), 0)
    path = [
        {
            "x": 3 * x + 2 * y,
            "y": 4 * x - 5 * y,
            "z": 0,
            "timestamp": max(generate_gaussian_integer(30, 5), 0),
            "type": 0,
        }
    ]
    return json.dumps(path)


async def get_bilicookies() -> dict:
    cookies, ts = await get_cookies_with_ts("bilibili")
    return cookies


def parse_bilibili_dynamic(dynamic: dict) -> dict:
    """
    解析B站动态数据，返回用于创建BiliBiliDynamic的数据字典

    Args:
        dynamic: B站动态原始数据

    Returns:
        包含解析后数据的字典
    """
    modules = dynamic["modules"]
    type_action = modules["module_author"]["pub_action"]
    id_str = str(dynamic["id_str"])  # 确保是字符串
    url = "http://m.bilibili.com/dynamic/" + id_str
    timestamp = modules["module_author"]["pub_ts"]
    uid = str(modules["module_author"]["mid"])  # 确保是字符串
    nickname = modules["module_author"]["name"]
    images = []
    content = ""
    is_opus = False

    if dyn := modules.get("module_dynamic"):
        if desc := dyn.get("desc"):
            if desc_text := desc.get("text"):
                content = desc_text
        if major := dyn.get("major"):
            match major["type"]:
                case "MAJOR_TYPE_DRAW":
                    draw = major["draw"]
                    if items := draw.get("items"):
                        for item in items:
                            if pic := item.get("src"):
                                images.append(pic)
                case "MAJOR_TYPE_ARCHIVE":
                    archive = major["archive"]
                    if pic := archive.get("cover"):
                        images.append(pic)
                    if desc := archive.get("desc"):
                        content = desc
                case "MAJOR_TYPE_OPUS":
                    opus = major["opus"]
                    if opus_pics := opus.get("pics"):
                        for pic in opus_pics:
                            if picurl := pic.get("url"):
                                images.append(picurl)
                    if summary := opus.get("summary"):
                        if summary_text := summary.get("text"):
                            content = summary_text
                    url = "https://m.bilibili.com/opus/" + str(id_str)
                    is_opus = True
                case "MAJOR_TYPE_ARTICLE":
                    article = major["article"]
                    if article_pics := article.get("covers"):
                        for pic in article_pics:
                            images.append(pic)
                    if desc := article.get("desc"):
                        content = desc
                case "MAJOR_TYPE_PGC":
                    pgc = major["pgc"]
                    if pic := pgc.get("cover"):
                        images.append(pic)
                    if title := pgc.get("title"):
                        content = title
                case "MAJOR_TYPE_COMMON":
                    common = major["common"]
                    if pic := common.get("cover"):
                        images.append(pic)
                    if desc := common.get("desc"):
                        content = desc
                case _:
                    pass

    return {
        "uid": uid,
        "id": id_str,
        "content": content,
        "images": images,
        "timestamp": timestamp,
        "url": url,
        "nickname": nickname,
        "dynamic": dynamic,
        "is_opus": is_opus,
        "type": type_action,
    }


@dataclass
class BiliBiliDynamic(Post):
    dynamic: dict = None
    is_opus: bool = False
    type: str = ""

    @classmethod
    def from_dict(cls, dynamic: dict) -> "BiliBiliDynamic":
        """从动态数据字典创建BiliBiliDynamic实例"""
        parsed_data = parse_bilibili_dynamic(dynamic)
        return cls(**parsed_data)

    @override
    async def get_referer(self) -> str:
        return "https://t.bilibili.com"

    @override
    async def get_message(
        self, with_screenshot: bool = True
    ) -> Sequence[Message | MessageSegment]:
        msg = [self.nickname + self.type]
        imgmsg = []
        img = None
        if with_screenshot:
            img = await get_bili_dynamic_screenshot(
                self.url, cookies=await get_bilicookies()
            )
            if img:
                msg.append(str(img))
        if not img:
            msg.append(self.content)
        await asyncio.sleep(0.5)
        msg.append(self.url)
        res = [Message("\n".join(msg))]
        if self.images:
            for pic in self.images:
                imgmsg.append(MessageSegment.image(pic))
        if imgmsg:
            res.append(Message(imgmsg))
        return res


async def get_new_dynamic(uid: str) -> BiliBiliDynamic | None:
    dyns = await get_dynamic(uid, 0)
    if dyns:
        return dyns[0]
    else:
        return None


async def get_dynamic(uid: str, ts) -> list[BiliBiliDynamic]:
    url = dynamic_url
    h = headers.copy()
    dm_img_str     = base64.b64encode(b"no webgl").decode()[:-2]
    dm_cover_img_str = base64.b64encode(b"no webgl").decode()[:-2]
    params = {
        "host_mid": int(uid),
        "timezone_offset": -480,
        "platform": "web",
        "offset": "",
        "features": "itemOpusStyle,listOnlyfans,opusBigCover,onlyfansVote",
        "dm_img_list": get_dm_img_list(),
        "dm_cover_img_str": dm_cover_img_str,
        "dm_img_str": dm_img_str,
    }
    try:
        code = 000
        res = await aiohttpx.get(
        url, params=params, headers=h, cookies=await get_bilicookies()
    )
        rj = res.json
        data = rj.get("data", {})
        code = int(rj.get("code", 0))
        if code == -352:
            res = await aiohttpx.get(
                url, params=params, headers=h, cookies=await get_bilicookies()
            )
            rj = res.json
            data = rj.get("data", {})
        cards = data.get("items", [])
    except Exception as e:
        sv.logger.error(f"获取动态数据解析失败: {e}, uid: {uid}, response: {res.text},code: {code},status: {res.status_code}")
        return []
    dyn = cards[4::-1]
    dyns = [BiliBiliDynamic.from_dict(d) for d in dyn]
    dyns = [d for d in dyns if d.timestamp > ts]
    dyns = sorted(dyns, key=lambda x: x.timestamp, reverse=True)
    return dyns


db_path = db_dir / "bilidata.db"
engine = create_engine(f"sqlite:///{db_path}", echo=False, future=True)
Session = sessionmaker(bind=engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class DynamicDB(Base):
    __tablename__ = "dynamicdb"
    uid: Mapped[str] = mapped_column(Text, primary_key=True)
    group: Mapped[int] = mapped_column(Integer, primary_key=True)
    time: Mapped[float] = mapped_column(Float, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)


# 初始化数据库
if not db_path.exists():
    Base.metadata.create_all(engine)
