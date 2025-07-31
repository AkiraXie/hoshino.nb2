import asyncio
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
from hoshino import db_dir, Message, MessageSegment, SUPERUSER
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
from functools import partial
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

# 异步锁，防止并发调用get_bilicookies时的竞态条件
_cookies_lock = asyncio.Lock()

headers = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.bilibili.com",
}


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
    cookies["buvid3"] = str(uuid.uuid1())
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
    res = dict(resp.cookies)
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


# 添加一个全局变量来跟踪刷新状态
_refreshing = False
_last_refresh_time = 0


async def get_bilicookies() -> dict:
    """
    获取B站cookies，尝试刷新过期的cookies
    :return: B站cookies字典
    """
    global _refreshing, _last_refresh_time

    async with _cookies_lock:
        cookies, ts = await get_cookies_with_ts("bilibili")
        if not cookies:
            return {}

        current_time = time.time()

        # 如果正在刷新中，直接返回现有cookies
        if _refreshing:
            sv.logger.info("正在刷新cookies中，返回现有cookies")
            return cookies

        # 检查是否需要刷新（超过1天且距离上次刷新超过5分钟）
        if (
            current_time - ts > 86400 * 1 and current_time - _last_refresh_time > 300
        ):  # 5分钟防重复刷新
            _refreshing = True
            _last_refresh_time = current_time

            try:
                sv.logger.info("B站cookies过期，尝试刷新...")
                res_cookies = await refresh_bili_cookies(cookies)
                if not res_cookies:
                    sv.logger.error("刷新B站cookies失败")
                    return cookies
                return res_cookies
            finally:
                _refreshing = False

        return cookies


@sv.on_command(
    "refreshbili",
    aliases={"refbili", "刷新bcookie", "刷新b站cookies"},
    only_group=False,
    only_to_me=True,
    permission=SUPERUSER,
)
async def refb():
    global _refreshing, _last_refresh_time

    async with _cookies_lock:
        if _refreshing:
            await send("正在刷新中，请稍后再试")
            return

        _refreshing = True
        _last_refresh_time = time.time()

        try:
            cks = await get_cookies("bilibili")
            res = await refresh_bili_cookies(cks)
            if res:
                await send("B站cookies刷新成功！")
            else:
                await send("B站cookies刷新失败，请检查日志。")
        finally:
            _refreshing = False


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
        "host_mid": uid,
        "timezone_offset": -480,
        "offset": "",
        "features": "itemOpusStyle,opusBigCover,onlyfansVote,endFooterHidden,decorationCard,onlyfansAssetsV2,ugcDelete,onlyfansQaCard,commentsNewVersion",
    }

    res = await aiohttpx.get(
        url, params=params, headers=h, cookies=await get_bilicookies()
    )
    rj = res.json
    data = rj.get("data", {})

    if not data:
        sv.logger.error(
            f"获取Bili动态失败 UID {uid}: 无数据返回, code: {rj.get('code', '未知')}"
        )
        return []
    cards = data.get("items", [])
    if not cards:
        sv.logger.error(
            f"获取Bili动态失败 UID {uid}: 无动态数据, code: {rj.get('code', '未知')}"
        )
        return []
    dyn = cards[4::-1]
    dyns = [BiliBiliDynamic.from_dict(d) for d in dyn]
    dyns = [d for d in dyns if d.timestamp > ts]
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
