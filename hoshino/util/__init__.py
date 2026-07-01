from __future__ import annotations
from pathlib import Path
import random
import pytz
import nonebot
from nonebot.log import logger
import unicodedata
import asyncio
import os
from asyncio import get_running_loop
from typing import List, Type, Sequence
from io import BytesIO
from collections import defaultdict
from PIL import Image
from datetime import datetime, timedelta
from nonebot.adapters import Event
from nonebot.typing import T_State
from nonebot.params import Depends
from hoshino import fav_dir, img_dir, hsn_nickname, video_dir
from nonebot.adapters import Bot
from nonebot.matcher import Matcher, current_bot, current_event
from hoshino.command import UniMessage
from hoshino.platform.ob11.types import OneBotV11Message, OneBotV11MessageSegment
from hoshino.platform import (
    Target,
    custom_node_segment,
    get_event_message,
    get_group_id,
    get_plaintext,
    get_reply_message,
    get_session_id,
    image_segment,
    get_user_id,
    group_target,
    is_group_event,
    is_private_event,
    send_group_forward,
    send_private_forward,
    send_to_target,
    video_segment,
)
from nonebot.matcher import current_matcher
from nonebot.permission import SUPERUSER
from nonebot.plugin import CommandGroup, on_command, on_message
from nonebot.rule import Rule, to_me
from nonebot.compat import type_validate_python
from . import aiohttpx
from sqlalchemy import Text, Float, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from hoshino import db_dir
from hoshino.core.hooks import on_post_startup
from time import time

__SU_IMGLIST = "__superuser__imglist"
__SU_VIDEOLIST = "__superuser__videolist"


def Cooldown(
    cooldown: float = 10,
    prompt: str | None = None,
) -> None:
    debounced = set()

    async def dependency(matcher: Matcher, event: Event, bot: Bot):
        loop = get_running_loop()
        key = get_user_id(event)
        if key is None:
            key = get_session_id(event)
        if key is None:
            key = str(id(event))
        message = prompt.format(cooldown) if prompt else f"请稍等 {cooldown} 秒后再试。"
        if key in debounced:
            await matcher.finish(message=message)
        else:
            debounced.add(key)
            loop.call_later(cooldown, lambda: debounced.discard(key))
        return

    return Depends(dependency)




def get_bot_list() -> Sequence[Bot]:
    return list(nonebot.get_bots().values())


async def _strip_cmd(bot: "Bot", event: "Event", state: T_State):
    message = get_event_message(event)
    segment = message.pop(0)
    segment_text = str(segment).lstrip()
    new_message = message.__class__(
        segment_text[len(state["_prefix"]["raw_command"]) :].lstrip()
    )  # type: ignore
    for new_segment in reversed(new_message):
        message.insert(0, new_segment)


def sucmd(
    name: str, only_to_me: bool = True, aliases: set | None = None, **kwargs
) -> Type[Matcher]:
    kwargs["aliases"] = aliases
    kwargs["permission"] = SUPERUSER
    kwargs["rule"] = to_me() if only_to_me else Rule()
    handlers = kwargs.pop("handlers", [])
    handlers.insert(0, _strip_cmd)
    kwargs["handlers"] = handlers
    kwargs.setdefault("block", True)
    kwargs["cmd"] = name
    return on_command(**kwargs)


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








def normalize_str(string: str) -> str:
    """
    规范化unicode字符串 并 转为小写
    """
    string = unicodedata.normalize("NFKC", string)
    string = string.lower()
    return string




async def _get_imgs_from_forward_msg(
    bot: Bot, msg: OneBotV11Message
) -> list[OneBotV11MessageSegment]:
    res = []
    for s in msg:
        if s.type == "forward":
            id_ = s.data["id"]
        else:
            continue
        dic: dict = await bot.get_forward_msg(id=id_)
        if dic:
            msgs = dic.get("message", dic.get("messages"))
            if msgs:
                for msg in msgs:
                    content = msg.get("content", msg.get("data", {}).get("content"))
                    if content:
                        content = type_validate_python(OneBotV11Message, content)
                        p = [
                            s for s in content if s.type == "image" or s.type == "mface"
                        ]
                        res.extend(p)

    return res


async def _get_videos_from_forward_msg(
    bot: Bot, msg: OneBotV11Message
) -> list[OneBotV11MessageSegment]:
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
                                content = type_validate_python(OneBotV11Message, content)
                                p = [s for s in content if s.type == "video"]
                                res.extend(p)
                if not msgs:
                    msgs = dic.get("messages")
                    for m in msgs:
                        content = type_validate_python(OneBotV11Message, m)
                        p = [
                            s for s in content if s.type == "image" or s.type == "mface"
                        ]
                        res.extend(p)
    return res




async def get_event_image_segments(
    bot: Bot, event: Event, state: T_State
) -> bool:
    msg = get_event_message(event, [])
    imglist = [s for s in msg if s.type == "image" or s.type == "mface"]
    imglist.extend(await get_image_segments_from_forward(bot, event))
    reply_message = get_reply_message(event)
    if reply_message:
        imglist.extend(
            [s for s in reply_message if s.type == "image" or s.type == "mface"]
        )
    if imglist:
        state[__SU_IMGLIST] = imglist
        return True
    return False




async def save_img(
    url: str, name: str | Path, fav: bool = False, verify: bool = False
) -> bool:
    if fav:
        idir = fav_dir
    else:
        idir = img_dir
    image_path = idir / name
    result = await save_img_by_path(url, image_path, verify=verify)
    return result is not None


async def save_video(url: str, name: str, verify: bool = False) -> bool:
    idir = video_dir
    video_path = idir / name
    result = await save_video_by_path(url, video_path, verify=verify)
    return result is not None


async def save_img_by_path(
    url: str, path: str | Path, verify: bool = False, headers={}
) -> Path | None:
    if path.parent and not path.parent.exists():
        os.makedirs(path.parent, exist_ok=True)
    r = await aiohttpx.get(url, verify=verify, headers=headers, follow_redirects=True)
    try:
        im = Image.open(bio := BytesIO(r.content))
        # 根据图片格式更改文件后缀
        if im.format:
            format_ext = im.format.lower()
            if format_ext == "jpeg":
                format_ext = "jpg"
            path = Path(path).with_suffix(f".{format_ext}")
        # GIF/WEBP 动图直接写入原始字节，避免丢失动画帧
        if im.format and im.format.upper() in ("GIF", "WEBP") and getattr(im, "is_animated", False):
            im.close()
            bio.close()
            with open(path, "wb") as f:
                f.write(r.content)
        else:
            im.save(path)
            im.close()
            bio.close()
        return path
    except Exception as e:
        nonebot.logger.error(f"保存图片失败: {e}")
    return None


async def save_video_by_path(
    url: str, path: str | Path, verify: bool = False, headers={}
) -> Path | None:
    r = await aiohttpx.get(url, verify=verify, headers=headers, follow_redirects=True)
    r.raise_for_status()
    video_signatures = [
        b"\x00\x00\x00\x18ftypmp4",
        b"\x1aE\xdf\xa3",
        b"FLV",
        b"GIF",
        b"RIFF",
        b"\x00\x00\x01\x00",
        b"ftypqt",
        b"moov",
    ]
    if len(r.content) < 200:
        nonebot.logger.error(f"视频文件过小，可能无效: {url}")
        return None

    # 检查视频文件的签名并确定格式
    is_video = False
    video_format = None

    for sig in video_signatures:
        if r.content.startswith(sig):
            is_video = True
            if sig == b"\x00\x00\x00\x18ftypmp4":
                video_format = "mp4"
            elif sig == b"\x1aE\xdf\xa3":
                video_format = "mkv"
            elif sig == b"FLV":
                video_format = "flv"
            elif sig == b"GIF":
                video_format = "gif"
            elif sig == b"RIFF":
                video_format = "avi"
            elif sig == b"ftypqt":
                video_format = "mov"
            elif sig == b"moov":
                video_format = "mov"
            break

    if not is_video:
        if (
            b"ftyp" in r.content[:50]
            or b"moov" in r.content[:50]
            or b"mdat" in r.content[:50]
        ):
            is_video = True
            video_format = "mp4"  # 默认为mp4格式

    # 根据检测到的格式更改文件后缀
    if is_video and video_format:
        path = Path(path).with_suffix(f".{video_format}")

    if not is_video:
        nonebot.logger.error("下载的文件不是视频格式")
        return None

    with open(path, "wb") as f:
        f.write(r.content)

    return path


def random_image_or_video_by_path(
    path: Path = img_dir,
    num: int = 12,
    seed: int | None = None,
    video: bool = False,
    keyword: str | None = None,
) -> list[OneBotV11MessageSegment]:
    files = []
    for file_path in path.iterdir():
        if file_path.is_file():
            # 如果提供了关键词，则筛选包含关键词的文件名
            if keyword and keyword.lower() not in file_path.name.lower():
                continue
            files.append(file_path.name)

    if not files:
        return []

    num = min(len(files), num)
    imgs = []
    ra = random.SystemRandom(seed)
    selected_names = ra.sample(files, k=num)
    for name in selected_names:
        fpath = path / name
        img = image_segment(fpath) if not video else video_segment(fpath)
        imgs.append(img)
    if imgs:
        names = []
        for i, name in enumerate(selected_names):
            names.append(f"{i + 1}: {name}")
        imgs.append("\n".join(names))
    return imgs






async def send_to_superuser(msg=""):
    bot: Bot = nonebot.get_bot()
    sus = bot.config.superusers
    for su in sus:
        await asyncio.sleep(0.5)
        await send_to_target(bot, Target(str(su), private=True), msg)




async def send(
    message: str | "OneBotV11Message" | "OneBotV11MessageSegment" | UniMessage,
    *,
    call_header: bool = False,
    at_sender: bool = False,
    **kwargs,
):
    matcher = current_matcher.get()
    if matcher is None:
        raise ValueError("No running matcher found!")
    if isinstance(message, UniMessage):
        await message.send(at_sender=at_sender, **kwargs)
        return
    await matcher.send(message, call_header=call_header, at_sender=at_sender, **kwargs)




async def send_segments(
    message: Sequence[OneBotV11Message | OneBotV11MessageSegment | str | UniMessage],
):
    if not message:
        return
    if len(message) == 1:
        await send(message[0])
        return
    if any(isinstance(item, UniMessage) for item in message):
        for item in message:
            await send(item)
            await asyncio.sleep(0.3)
        return
    bot = current_bot.get()
    event = current_event.get()
    nodes = construct_nodes(user_id=int(bot.self_id), segments=message)
    if (group_id := get_group_id(event)) is not None:
        await send_group_forward(bot, group_id, nodes)
    elif (user_id := get_user_id(event)) is not None:
        await send_private_forward(bot, user_id, nodes)
    else:
        return


async def send_group_segments(
    bot: Bot,
    group_id: int,
    message: Sequence[OneBotV11Message | OneBotV11MessageSegment | str | UniMessage],
):
    if not message:
        return
    if len(message) == 1:
        await send_to_target(bot, group_target(group_id), message[0])
        return
    if any(isinstance(item, UniMessage) for item in message):
        target = group_target(group_id)
        for item in message:
            await send_to_target(bot, target, item)
            await asyncio.sleep(0.3)
        return
    nodes = construct_nodes(user_id=int(bot.self_id), segments=message)
    await send_group_forward(bot, group_id, nodes)


async def finish(
    message: str | "OneBotV11Message" | "OneBotV11MessageSegment" | None = None,
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


db_dir.mkdir(parents=True, exist_ok=True)
db_path = db_dir / "cookies.db"
engine = create_engine(f"sqlite:///{db_path}", echo=False, future=True)
Session = sessionmaker(bind=engine, expire_on_commit=False)

# 初始化数据库
if not db_path.exists():
    Base.metadata.create_all(engine)

cookiejar: dict[str, str] = {}

_cookies_lock = asyncio.Lock()


async def save_cookies(name: str, cookies: str | dict):
    if isinstance(cookies, dict):
        cookies = "; ".join(f"{k}={v}" for k, v in cookies.items())
    cookiejar[name] = cookies
    async with _cookies_lock:
        with Session() as session:
            obj: Cookies | None = session.get(Cookies, name)
            if obj:
                obj.cookie = cookies
                obj.created_at = time()
            else:
                obj = Cookies(name=name, cookie=cookies, created_at=time())
                session.add(obj)
            session.commit()


async def delete_cookies(name: str):
    res = cookiejar.pop(name, None)
    async with _cookies_lock:
        with Session() as session:
            obj: Cookies | None = session.get(Cookies, name)
            if obj:
                session.delete(obj)
                session.commit()
    return res


def check_cookies(name: str) -> bool:
    with Session() as session:
        stmt = select(Cookies).where(Cookies.name == name)
        row = session.execute(stmt).scalar_one_or_none()
        if row:
            if not row.created_at:
                return False

            if time() - row.created_at > 86400 * 7:
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
            if not row.created_at or time() - row.created_at > 86400 * 7:
                session.delete(row)
                res[row.name] = False
                cookiejar.pop(row.name, None)
            else:
                res[row.name] = True
                cookiejar[row.name] = row.cookie
        session.commit()
    return res


async def get_cookies_with_ts(name: str) -> tuple[dict, float]:
    try:
        if name in cookiejar:
            cookies = cookiejar[name]
        else:
            with Session() as session:
                stmt = select(Cookies).where(Cookies.name == name)
                row = session.execute(stmt).scalar_one_or_none()
                if not row:
                    return {}, 0
                cookies = row.cookie
                ts = row.created_at
        if not cookies:
            return {}, 0
        cookie_dict = {}
        for item in cookies.split("; "):
            key, value = item.split("=", 1)
            cookie_dict[key] = value
        return cookie_dict, ts
    except Exception:
        return {}, 0


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
                if time() - ts > 86400 * 7:
                    session.delete(row)
                    session.commit()
                    cookiejar.pop(name, None)
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
    resp = await aiohttpx.get(
        url, follow_redirects=False, headers=headers, verify=False
    )
    loc = resp.headers.get("Location")
    if not loc:
        return url
    return loc


