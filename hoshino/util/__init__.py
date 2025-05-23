import random
import pytz
import zhconv
import nonebot
import unicodedata
import os
from asyncio import get_running_loop
from typing import List, Optional, Type, Union
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
from hoshino import fav_dir, img_dir, hsn_nickname
from nonebot.matcher import Matcher, current_matcher, current_bot, current_event
from nonebot.permission import SUPERUSER
from nonebot.plugin import CommandGroup, on_command, on_message
from nonebot.rule import Rule, to_me
from nonebot.compat import type_validate_python
from . import aiohttpx
from peewee import SqliteDatabase, Model, TextField, CompositeKey, FloatField
from hoshino import db_dir, on_startup
from time import time

__SU_IMGLIST = "__superuser__imglist"


def Cooldown(
    cooldown: float = 10,
    prompt: Optional[str] = None,
) -> None:
    debounced = set()

    async def dependency(matcher: Matcher, event: MessageEvent, bot: Bot):
        loop = get_running_loop()
        key = event.user_id
        if key in debounced:
            await matcher.finish(prompt.format(cooldown))
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


def get_bot_list() -> List[Bot]:
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
    规范化unicode字符串 并 转为小写 并 转为简体
    """
    string = unicodedata.normalize("NFKC", string)
    string = string.lower()
    string = zhconv.convert(string, "zh-hans")
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
                                content: list[dict]
                                content = type_validate_python(Message, content)
                                p = [
                                    s
                                    for s in content
                                    if s.type == "image" or s.type == "mface"
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
    user_id: int, segments: List[Message | MessageSegment | str]
) -> Message:
    def node(content):
        return MessageSegment.node_custom(
            user_id=user_id, nickname=hsn_nickname, content=content
        )

    return Message([node(seg) for seg in segments])


async def send_segments(
    message: List[Message | MessageSegment | str],
):
    if len(message) == 1:
        await send(message[0])
        return
    bot: Bot = current_bot.get()
    event: MessageEvent = current_event.get()
    api = ""
    nodes = construct_nodes(user_id=int(bot.self_id), segments=message)
    kwargs = {"messages": nodes}
    if isinstance(event, GroupMessageEvent):
        kwargs["group_id"] = event.group_id
        api = "send_group_forward_msg"
    else:
        kwargs["user_id"] = event.user_id
        api = "send_private_forward_msg"
    await bot.call_api(api, **kwargs)


async def send_group_segments(
    bot: Bot,
    group_id: int,
    message: List[Message | MessageSegment | str],
):
    if len(message) == 1:
        await bot.send_group_msg(group_id=group_id, message=message[0])
        return
    nodes = construct_nodes(user_id=int(bot.self_id), segments=message)
    kwargs = {"messages": nodes}
    kwargs["group_id"] = group_id
    api = "send_group_forward_msg"
    await bot.call_api(api, **kwargs)


async def finish(
    message: Union[str, "Message", "MessageSegment"],
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


db_path = db_dir + "cookies.db"
db = SqliteDatabase(db_path)


class Cookies(Model):
    name = TextField()
    cookie = TextField()
    created_at = FloatField()

    class Meta:
        primary_key = CompositeKey("name")
        database = db


db.connect()
db.create_tables([Cookies], safe=True)


cookiejar = {}


def save_cookies(name: str, cookies: Union[str, dict]):
    if isinstance(cookies, dict):
        cookies = "; ".join(f"{k}={v}" for k, v in cookies.items())
    cookiejar[name] = cookies
    Cookies.replace(name=name, cookie=cookies, created_at=time()).execute()


async def get_cookies(name: str) -> dict:
    try:
        if name in cookiejar:
            cookies = cookiejar[name]
        else:
            rows = Cookies.get_or_none(Cookies.name == name)
            if not rows:
                return {}
            cookies = rows.cookie
            ts = rows.created_at
            if time() - ts > 86400 * 2:
                Cookies.delete().where(Cookies.name == name).execute()
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
        if name == "bilibili":
            cookie_dict = {"SESSDATA": cookie_dict.get("SESSDATA", "").strip()}
        return cookie_dict
    except Exception:
        return {}


async def get_redirect(url: str, headers={}) -> str | None:
    resp = await aiohttpx.head(url, follow_redirects=False, headers=headers)
    loc = resp.headers.get("Location")
    if not loc:
        return None
    return loc


@on_startup
async def init_cookies():
    await get_cookies("xhs")
    await get_cookies("weibo")
    await get_cookies("bilibili")
