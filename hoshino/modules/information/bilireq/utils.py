import asyncio
import random
import re
import uuid
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
    SUPERUSER,
    scheduled_job,
    on_startup,
)
from hoshino.service import Service
from hoshino.util import (
    aiohttpx,
    get_cookies,
    get_cookies_with_ts,
    save_cookies,
    send,
    send_to_superuser,
)
from hoshino.util.playwrights import get_bili_dynamic_screenshot
from urllib.parse import urlencode
from hashlib import md5
from functools import reduce
from ..utils import Post
from typing import Sequence
from dataclasses import dataclass

from Cryptodome.Cipher import PKCS1_OAEP
from Cryptodome.Hash import SHA256
from Cryptodome.PublicKey import RSA
import time
import binascii

sv = Service("bilireq", enable_on_default=False)
info_url = "https://api.bilibili.com/x/space/wbi/acc/info"
dynamic_url = "https://api.bilibili.com/x/polymer/web-dynamic/v1/feed/space"
live_url = "https://api.live.bilibili.com/room/v1/Room/get_status_info_by_uids"
refresh_csrf_url = "https://www.bilibili.com/correspond/1/{}"
refresh_cookie_url = "https://passport.bilibili.com/x/passport-login/web/cookie/refresh"
nav_url = "https://api.bilibili.com/x/web-interface/nav"

# 异步锁，防止并发调用get_bilicookies时的竞态条件
_cookies_lock = asyncio.Lock()

headers = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0"
    ),
    "Referer": "https://www.bilibili.com",
}
mixinKeyEncTab = [
    46,
    47,
    18,
    2,
    53,
    8,
    23,
    32,
    15,
    50,
    10,
    31,
    58,
    3,
    45,
    35,
    27,
    43,
    5,
    49,
    33,
    9,
    42,
    19,
    29,
    28,
    14,
    39,
    12,
    38,
    41,
    13,
    37,
    48,
    7,
    16,
    24,
    55,
    40,
    61,
    26,
    17,
    0,
    1,
    60,
    51,
    30,
    4,
    22,
    25,
    54,
    21,
    56,
    59,
    6,
    63,
    57,
    62,
    11,
    36,
    20,
    34,
    44,
    52,
]
imgsubkey = ""


@on_startup
@scheduled_job("cron", hour="0", minute="5")
async def _refresh_wbi_key():
    url = nav_url
    resp = await aiohttpx.get(
        url,
        headers=headers,
    )
    rj = resp.json
    img_url: str = rj["data"]["wbi_img"]["img_url"]
    sub_url: str = rj["data"]["wbi_img"]["sub_url"]
    img_key = img_url.rsplit("/", 1)[1].split(".")[0]
    sub_key = sub_url.rsplit("/", 1)[1].split(".")[0]
    global imgsubkey
    imgsubkey = img_key + sub_key
    sv.logger.info(f"wbi key refreshed: {imgsubkey}")


async def _enc_wbi(params: dict) -> dict:
    dm_rand = "ABCDEFGHIJK"
    p = params.copy()
    p.update(
        {
            "dm_img_list": "[]",  # 鼠标/键盘操作记录
            "dm_img_str": "".join(random.sample(dm_rand, 2)),
            "dm_cover_img_str": "".join(random.sample(dm_rand, 2)),
            "dm_img_inter": '{"ds":[],"wh":[0,0,0],"of":[0,0,0]}',
        }
    )
    params = p

    def getMixinKey(orig: str):
        return reduce(lambda s, i: s + orig[i], mixinKeyEncTab, "")[:32]

    mixin_key = getMixinKey(imgsubkey)
    params["wts"] = round(time.time())
    if not params.get("web_location"):
        params["web_location"] = 1550101
    params = dict(sorted(params.items()))
    params = {
        k: "".join(filter(lambda chr: chr not in "!'()*", str(v)))
        for k, v in params.items()
    }
    query = urlencode(params)  # 序列化参数
    wbi_sign = md5((query + mixin_key).encode()).hexdigest()  # 计算 w_rid
    params["w_rid"] = wbi_sign
    return params


def _getCorrespondPath() -> str:
    key = RSA.importKey(
        """\
-----BEGIN PUBLIC KEY-----
MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQDLgd2OAkcGVtoE3ThUREbio0Eg
Uc/prcajMKXvkCKFCWhJYJcLkcM2DKKcSeFpD/j6Boy538YXnR6VhcuUJOhH2x71
nzPjfdTcqMz7djHum0qSZA0AyCBDABUqCrfNgCiJ00Ra7GmRj+YCK1NJEuewlb40
JNrRuoEUXpabUzGB8QIDAQAB
-----END PUBLIC KEY-----"""
    )
    ts = round(time.time() * 1000)
    cipher = PKCS1_OAEP.new(key, SHA256)
    encrypted = cipher.encrypt(f"refresh_{ts}".encode())
    return binascii.b2a_hex(encrypted).decode()


async def _get_refresh_csrf(cookies: dict) -> str | None:
    correspond_path = _getCorrespondPath()
    url = refresh_csrf_url.format(correspond_path)
    cookies["buvid3"] = str(uuid.uuid1())
    resp = await aiohttpx.get(
        url,
        headers=headers,
        cookies=cookies,
    )
    if resp.status_code == 404:
        sv.logger.error("refresh csrf error: correspondPath 过期或错误。")
        return None
    elif resp.ok:
        text = resp.text
        refresh_csrf = re.findall('<div id="1-name">(.+?)</div>', text)[0]
        return refresh_csrf
    else:
        sv.logger.error(f"refresh csrf error: {resp.status_code} {resp.text}")
        return None


async def _refresh_cookies(cookies: dict) -> dict:
    url = refresh_cookie_url
    refresh_csrf = await _get_refresh_csrf(cookies)
    data = {
        "csrf": cookies["bili_jct"],
        "refresh_csrf": refresh_csrf,
        "refresh_token": cookies["ac_time_value"],
        "source": "main_web",
    }
    resp = await aiohttpx.post(
        url,
        cookies=cookies,
        data=data,
        headers=headers,
    )
    if not resp.ok:
        sv.logger.error(f"refresh cookies error: {resp.status_code} {resp.text}")
        return {}
    rj = resp.json
    res = cookies.copy()
    res.update(resp.cookies)
    res["ac_time_value"] = rj.get("data", {}).get("refresh_token", "")
    return res


async def _confirm_refresh(cookies: dict) -> bool:
    """
    确认刷新B站cookies是否成功
    :param cookies: B站cookies字典
    :return: 是否刷新成功
    """
    try:
        data = {
            "csrf": cookies.get("bili_jct", ""),
            "refresh_token": cookies.get("ac_time_value", ""),
        }
        url = "https://passport.bilibili.com/x/passport-login/web/confirm/refresh"
        resp = await aiohttpx.post(url, data=data, cookies=cookies, headers=headers)
        if not resp.ok:
            sv.logger.error("B站cookies已失效，无法确认刷新。")
            return False
        rj = resp.json
        if rj.get("code") != 0:
            sv.logger.error(f"确认刷新B站cookies失败, json:{rj}")
            return False
        return True
    except Exception as e:
        sv.logger.error(f"确认刷新B站cookies时发生错误: {e}")
        return False


async def refresh_bili_cookies(cookies: dict) -> dict:
    """
    刷新B站cookies
    :param cookies: 原始cookies字典
    :return: 刷新后的cookies字典
    """
    try:
        new_cookies = await _refresh_cookies(cookies)
        if not new_cookies:
            sv.logger.error("刷新B站cookies失败，返回空字典。")
            return {}

        if not await _confirm_refresh(new_cookies):
            sv.logger.error("确认刷新B站cookies失败，返回原始cookies。")
            return cookies

        # 确保原子性地保存cookies
        save_cookies("bilibili", new_cookies)
        sv.logger.info("B站cookies刷新成功")
        return new_cookies

    except Exception as e:
        sv.logger.error(f"刷新B站cookies时发生错误: {e}")
        return {}


async def get_bilicookies() -> dict:
    """
    获取B站cookies，尝试刷新过期的cookies
    :return: B站cookies字典
    """
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
    params = {
        "host_mid": int(uid),
        "timezone_offset": -480,
        "offset": "",
        "features": "itemOpusStyle",
    }
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
