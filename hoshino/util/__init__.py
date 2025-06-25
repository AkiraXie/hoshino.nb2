from __future__ import annotations
import random
import pytz
import nonebot
import unicodedata
import os
from asyncio import get_running_loop
from typing import List, Optional, Type, Union, Sequence
from io import BytesIO
from collections import defaultdict
from PIL import Image
from datetime import datetime, timedelta
from nonebot.adapters.onebot.v11 import MessageSegment, Message, Bot
from nonebot.params import Depends
from nonebot.adapters.onebot.v11.event import (
    Event,
    GroupMessageEvent,
    PrivateMessageEvent,
    MessageEvent,
)
from nonebot.typing import T_State
from hoshino import fav_dir, img_dir, hsn_nickname, video_dir
from nonebot.matcher import Matcher, current_matcher, current_bot, current_event
from nonebot.permission import SUPERUSER
from nonebot.plugin import CommandGroup, on_command, on_message
from nonebot.rule import Rule, to_me
from nonebot.compat import type_validate_python
from . import aiohttpx
from sqlalchemy import Column, Text, Float, create_engine, PrimaryKeyConstraint, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from hoshino import db_dir, on_bot_connect
from time import time

__SU_IMGLIST = "__superuser__imglist"
__SU_VIDEOLIST = "__superuser__videolist"

def Cooldown(
    cooldown: float = 10,
    prompt: Optional[str] = None,
) -> None:
    debounced = set()

    async def dependency(matcher: Matcher, event: MessageEvent, bot: Bot):
        loop = get_running_loop()
        key = event.user_id
        message = prompt.format(cooldown) if prompt else f"请稍等 {cooldown} 秒后再试。"
        if key in debounced:
            await matcher.finish(message=message)
        else:
            debounced.add(key)
            loop.call_later(cooldown, lambda: debounced.discard(key))
        return

    return Depends(dependency)


class DailyNumberLimiter:
    tz = pytz.timezone("Asia/Shanghai")

    def __init__(self, max_num):
        self.today = -1
        self.count = defaultdict(int)
        self.max = max_num

    def check(self, key) -> bool:
        now = datetime.now(self.tz)
        day = (now - timedelta(hours=5)).day
        if day != self.today:
            self.today = day
            self.count.clear()
        return bool(self.count[key] < self.max)

    def get_num(self, key):
        return self.count[key]

    def increase(self, key, num=1):
        self.count[key] += num

    def reset(self, key):
        self.count[key] = 0


def get_bot_list() -> Sequence[Bot]:
    return list(nonebot.get_bots().values())


async def _strip_cmd(bot: "Bot", event: "Event", state: T_State):
    message = event.get_message()
    segment = message.pop(0)
    segment_text = str(segment).lstrip()
    new_message = message.__class__(
        segment_text[len(state["_prefix"]["raw_command"]) :].lstrip()
    )  # type: ignore
    for new_segment in reversed(new_message):
        message.insert(0, new_segment)


def sucmd(
    name: str, only_to_me: bool = True, aliases: Optional[set] = None, **kwargs
) -> Type[Matcher]:
    kwargs["aliases"] = aliases
    kwargs["permission"] = SUPERUSER
    kwargs["rule"] = to_me() if only_to_me else Rule()
    handlers = kwargs.pop("handlers", [])
    handlers.insert(0, _strip_cmd)
    kwargs["handlers"] = handlers
    kwargs.setdefault("block", True)
    return on_command(name, **kwargs)


def sucmds(name: str, only_to_me: bool = False, **kwargs) -> CommandGroup:
    kwargs["permission"] = SUPERUSER
    kwargs["rule"] = to_me() if only_to_me else Rule()
    handlers = kwargs.pop("handlers", [])
    handlers.insert(0, _strip_cmd)
    kwargs["handlers"] = handlers
    kwargs.setdefault("block", True)
    return CommandGroup(name, **kwargs)


def sumsg(
    only_to_me: bool = True,
    rule: Rule = Rule(),
    **kwargs,
) -> Type[Matcher]:
    kwargs["permission"] = SUPERUSER
    rule = rule & to_me() if only_to_me else Rule(rule)
    kwargs["rule"] = rule
    kwargs.setdefault("block", True)
    return on_message(**kwargs)


def img_to_bytes(pic: Image.Image) -> bytes:
    buf = BytesIO()
    pic.save(buf, format="PNG")
    return buf.getvalue()


def img_to_segment(pic: Image.Image) -> MessageSegment:
    return MessageSegment.image(img_to_bytes(pic))


def concat_pic(pics, border=5):
    num = len(pics)
    w, h = pics[0].size
    des = Image.new("RGBA", (w, num * h + (num - 1) * border), (255, 255, 255, 255))
    for i, pic in enumerate(pics):
        des.paste(pic, (0, i * (h + border)), pic)
    return des


def normalize_str(string: str) -> str:
    """
    规范化unicode字符串 并 转为小写
    """
    string = unicodedata.normalize("NFKC", string)
    string = string.lower()
    return string


async def parse_qq(bot: Bot, event: Event, state: T_State):
    ids = []
    if isinstance(event, GroupMessageEvent):
        for m in event.get_message():
            if m.type == "at" and m.data["qq"] != "all":
                ids.append(int(m.data["qq"]))
        for m in event.get_plaintext().split():
            if m.isdigit():
                ids.append(int(m))
    elif isinstance(event, PrivateMessageEvent):
        for m in event.get_plaintext().split():
            if m.isdigit():
                ids.append(int(m))
    if ids:
        state["ids"] = ids.copy()


async def _get_imgs_from_forward_msg(bot: Bot, msg: Message) -> list[MessageSegment]:
    res = []
    for s in msg:
        if s.type == "forward":
            id_ = s.data["id"]
            dic = await bot.get_forward_msg(id=id_)
            if dic:
                msgs = dic.get("message")
                if msgs:
                    for msg in msgs:
                        data = msg.get("data")
                        if data:
                            content = data.get("content")
                            if content:
                                content = type_validate_python(Message, content)
                                p = [
                                    s
                                    for s in content
                                    if s.type == "image" or s.type == "mface"
                                ]
                                res.extend(p)
    return res

async def _get_videos_from_forward_msg(bot: Bot, msg: Message) -> list[MessageSegment]:
    res = []
    for s in msg:
        if s.type == "forward":
            id_ = s.data["id"]
            dic = await bot.get_forward_msg(id=id_)
            if dic:
                msgs = dic.get("message")
                if msgs:
                    for msg in msgs:
                        data = msg.get("data")
                        if data:
                            content = data.get("content")
                            if content:
                                content = type_validate_python(Message, content)
                                p = [
                                    s
                                    for s in content
                                    if s.type == "video"
                                ]
                                res.extend(p)
    return res


async def get_image_segments_from_forward(
    bot: Bot, event: MessageEvent
) -> list[MessageSegment]:
    res = []
    msg = event.get_message()
    if msg:
        res.extend(await _get_imgs_from_forward_msg(bot, msg))
    reply = event.reply
    if reply:
        res.extend(await _get_imgs_from_forward_msg(bot, reply.message))
    return res


async def get_event_image_segments(
    bot: Bot, event: MessageEvent, state: T_State
) -> bool:
    msg = event.get_message()
    imglist = [s for s in msg if s.type == "image" or s.type == "mface"]
    imglist.extend(await get_image_segments_from_forward(bot, event))
    reply = event.reply
    if reply:
        imglist.extend(
            [s for s in reply.message if s.type == "image" or s.type == "mface"]
        )
    if imglist:
        state[__SU_IMGLIST] = imglist
        return True
    return False


def get_event_image(event: MessageEvent) -> list[str]:
    msg = event.get_message()
    reply = event.reply
    imglist = [s.data["file"] for s in msg if s.type == "image" and "file" in s.data]
    if reply:
        imglist.extend([s.data["file"] for s in reply.message if s.type == "image"])
    return imglist


async def save_img(
    url: str, name: str, fav: bool = False, verify: bool = False
) -> bool:
    if fav:
        idir = fav_dir
    else:
        idir = img_dir
    r = await aiohttpx.get(url, verify=verify)
    try:
        im = Image.open(bio := BytesIO(r.content))
        name = os.path.join(idir, name)
        im.save(name)
        im.close()
        bio.close()
        return True
    except Exception as e:
        nonebot.logger.error(f"保存图片失败: {e}")
    return False

async def save_video(
    url: str, name: str, verify: bool = False
) -> bool:
    idir = video_dir
    r = await aiohttpx.get(url, verify=verify)
    video_signatures = [
                b'\x00\x00\x00\x18ftypmp4',  
                b'\x1aE\xdf\xa3',            
                b'FLV',                    
                b'GIF',                     
                b'RIFF',                     
                b'\x00\x00\x01\x00',         
                b'ftypqt',                  
                b'moov',                     
    ]
    if len(r.content) < 200: 
        nonebot.logger.error(f"视频文件过小，可能无效: {url}")
        return False
    
    # 检查视频文件的签名
    is_video = False
    for sig in video_signatures:
        if r.content.startswith(sig):
            is_video = True
            break
            
    if not is_video :
        if b'ftyp' in r.content[:50] or b'moov' in r.content[:50] or b'mdat' in r.content[:50]:
            is_video = True
    
    if not is_video:
        nonebot.logger.error("下载的文件不是视频格式")
        return False
        
    video_path = os.path.join(idir, name)
    with open(video_path, 'wb') as f:
        f.write(r.content)
    
    return True



def random_modify_pixel(img: Image.Image):
    i, j = random.randint(0, img.size[0]), random.randint(0, img.size[1])
    rand_color = random.choices(range(256), k=3)
    img.putpixel((i, j), tuple(rand_color))


def get_event_imageurl(event: MessageEvent) -> List[str]:
    msg = event.message
    imglist = [s.data.get("url", s.data.get("file")) for s in msg if s.type == "image"]
    return imglist


async def send_to_superuser(msg=""):
    bot = nonebot.get_bot()
    sus = bot.config.superusers
    for su in sus:
        await bot.send_private_msg(user_id=int(su), message=msg)


async def get_img_from_url(url: str) -> MessageSegment:
    resp = await aiohttpx.get(url)
    return MessageSegment.image(resp.content)


async def send(
    message: Union[str, "Message", "MessageSegment"],
    *,
    call_header: bool = False,
    at_sender: bool = False,
    **kwargs,
):
    matcher = current_matcher.get()
    if matcher is None:
        raise ValueError("No running matcher found!")
    await matcher.send(message, call_header=call_header, at_sender=at_sender, **kwargs)


def construct_nodes(
    user_id: int, segments: Sequence[Message | MessageSegment | str]
) -> Message:
    def node(content):
        return MessageSegment.node_custom(
            user_id=user_id, nickname=hsn_nickname, content=content
        )

    return Message([node(seg) for seg in segments])


async def send_segments(
    message: Sequence[Message | MessageSegment | str],
):
    if not message:
        return
    if len(message) == 1:
        await send(message[0])
        return
    bot = current_bot.get()
    event = current_event.get()
    nodes = construct_nodes(user_id=int(bot.self_id), segments=message)
    if isinstance(event, GroupMessageEvent):
        await bot.call_api(
            "send_group_forward_msg", group_id=event.group_id, messages=nodes
        )
    elif isinstance(event, PrivateMessageEvent):
        await bot.call_api(
            "send_private_forward_msg", user_id=event.user_id, messages=nodes
        )
    else:
        return


async def send_group_segments(
    bot: Bot,
    group_id: int,
    message: Sequence[Message | MessageSegment | str],
):
    if not message:
        return
    if len(message) == 1:
        await bot.send_group_msg(group_id=group_id, message=message[0])
        return
    nodes = construct_nodes(user_id=int(bot.self_id), segments=message)
    api = "send_group_forward_msg"
    await bot.call_api(api, messages=nodes, group_id=group_id)


async def finish(
    message: Union[str, "Message", "MessageSegment", None] = None,
    *,
    call_header: bool = False,
    at_sender: bool = False,
    **kwargs,
):
    matcher = current_matcher.get()
    if matcher is None:
        raise ValueError("No running matcher found!")
    await matcher.finish(
        message, call_header=call_header, at_sender=at_sender, **kwargs
    )


class Base(DeclarativeBase):
    pass


class Cookies(Base):
    __tablename__ = "cookies"
    name: Mapped[str] = mapped_column(Text, primary_key=True)
    cookie: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[float] = mapped_column(Float, nullable=False)


db_path = db_dir / "cookies.db"
engine = create_engine(f"sqlite:///{db_path}", echo=False, future=True)
Session = sessionmaker(bind=engine, expire_on_commit=False)

# 初始化数据库
if not db_path.exists():
    Base.metadata.create_all(engine)

cookiejar: dict[str, str] = {}


def save_cookies(name: str, cookies: Union[str, dict]):
    if isinstance(cookies, dict):
        cookies = "; ".join(f"{k}={v}" for k, v in cookies.items())
    cookiejar[name] = cookies
    with Session() as session:
        obj: Cookies | None = session.get(Cookies, name)
        if obj:
            obj.cookie = cookies
            obj.created_at = time()
        else:
            obj = Cookies(name=name, cookie=cookies, created_at=time())
            session.add(obj)
        session.commit()


def check_cookies(name: str) -> bool:
    with Session() as session:
        stmt = select(Cookies).where(Cookies.name == name)
        row = session.execute(stmt).scalar_one_or_none()
        if row:
            if not row.created_at:
                return False
            # 检查创建时间是否超过两天
            if time() - row.created_at > 86400 * 2:
                return False
            cookiejar[name] = row.cookie
            return True
    return False


def check_all_cookies() -> dict[str, bool]:
    res = {}
    with Session() as session:
        stmt = select(Cookies)
        rows = session.execute(stmt).scalars().all()
        for row in rows:
            if not row.created_at or time() - row.created_at > 86400 * 2:  # 超过两天
                session.delete(row)
                res[row.name] = False
                cookiejar.pop(row.name, None)
            else:
                res[row.name] = True
                cookiejar[row.name] = row.cookie
        session.commit()
    return res


async def get_cookies(name: str) -> dict:
    try:
        if name in cookiejar:
            cookies = cookiejar[name]
        else:
            with Session() as session:
                stmt = select(Cookies).where(Cookies.name == name)
                row = session.execute(stmt).scalar_one_or_none()
                if not row:
                    return {}
                cookies = row.cookie
                ts = row.created_at
                if time() - ts > 86400 * 3:
                    session.delete(row)
                    session.commit()
                    cookiejar.pop(name, None)
                    await send_to_superuser(f"cookie {name} 已过期,请重新设置")
                    return {}
                cookiejar[name] = cookies
        if not cookies:
            return {}
        cookie_dict = {}
        for item in cookies.split("; "):
            key, value = item.split("=", 1)
            cookie_dict[key] = value
        return cookie_dict
    except Exception:
        return {}


async def get_redirect(url: str, headers={}) -> str | None:
    resp = await aiohttpx.head(url, follow_redirects=False, headers=headers)
    loc = resp.headers.get("Location")
    if not loc:
        return None
    return loc


@on_bot_connect
async def init_cookies():
    await get_cookies("xhs")
    await get_cookies("weibo")
    await get_cookies("bilibili")
    dic = check_all_cookies()
    await send_to_superuser(
        "加载 cookies 完成, 当前可用 cookies: "
        + ", ".join(k for k, v in dic.items() if v)
    )
