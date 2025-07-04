import asyncio
from nonebot.typing import override
from sqlalchemy import (
    Float,
    Integer,
    Text,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from hoshino import db_dir, Message, MessageSegment
from hoshino.util import aiohttpx, get_cookies
from hoshino.util.playwrights import get_bili_dynamic_screenshot
from functools import partial
from ..utils import Post
from typing import Sequence
from dataclasses import dataclass

info_url = "https://api.bilibili.com/x/space/wbi/acc/info"
dynamic_url = "https://api.bilibili.com/x/polymer/web-dynamic/v1/feed/space"
live_url = "https://api.live.bilibili.com/room/v1/Room/get_status_info_by_uids"

headers = {
    "user-agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
    ),
}


get_bilicookies = partial(get_cookies, "bilibili")


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
    data = res.json.get("data", {})

    if not data:
        return []
    cards = data.get("items", [])
    if not cards:
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
