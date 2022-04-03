"""
Author: AkiraXie
Date: 2021-01-28 14:29:01
LastEditors: AkiraXie
LastEditTime: 2022-02-16 22:16:28
Description: 
Github: http://github.com/AkiraXie/
"""
import random
import pytz
import base64
import zhconv
import nonebot
import unicodedata
import time
import os
from typing import List, Optional, Tuple, Type, Union
from io import BytesIO
from collections import defaultdict
from PIL import Image, ImageDraw, ImageFont
from datetime import datetime, timedelta
from nonebot.adapters.onebot.v11 import MessageSegment,Message
from nonebot.adapters.onebot.v11.event import (
    Event,
    GroupMessageEvent,
    PrivateMessageEvent,
    MessageEvent,
)
from nonebot.typing import T_State
from hoshino import R,fav_dir,img_dir
from nonebot.utils import run_sync
from nonebot.adapters.onebot.v11 import Bot
from nonebot.matcher import Matcher, current_matcher
from nonebot.permission import SUPERUSER
from nonebot.plugin import CommandGroup, on_command
from nonebot.rule import Rule, to_me
from .aiohttpx import get
from .playwrights import get_bili_dynamic_screenshot

DEFAULTFONT = ImageFont.truetype(
    R.img("priconne/gadget/SourceHanSans-Regular.ttc"), size=48
)


class FreqLimiter:
    def __init__(self, default_cd_seconds):
        self.next_time = defaultdict(float)
        self.default_cd = default_cd_seconds

    def check(self, key) -> bool:
        return bool(time.time() >= self.next_time[key])

    def start_cd(self, key, cd_time=0):
        self.next_time[key] = time.time() + (
            cd_time if cd_time > 0 else self.default_cd
        )


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
        segment_text[len(state["_prefix"]["raw_command"]):].lstrip()
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
    return on_command(name, _depth=1, **kwargs)


def sucmds(name: str, only_to_me: bool = False, **kwargs) -> CommandGroup:
    kwargs["permission"] = SUPERUSER
    kwargs["rule"] = to_me() if only_to_me else Rule()
    handlers = kwargs.pop("handlers", [])
    handlers.insert(0, _strip_cmd)
    kwargs["handlers"] = handlers
    kwargs.setdefault("block", True)
    return CommandGroup(name, **kwargs)


def get_text_size(
    text: str,
    font: ImageFont.ImageFont = DEFAULTFONT,
    padding: Tuple[int, int, int, int] = (20, 20, 20, 20),
    spacing: int = 5,
) -> tuple:
    """
    返回文本转图片的图片大小

    *`text`：用来转图的文本

    *`font`：一个`ImageFont`实例

    *`padding`：一个四元`int`元组，分别是左、右、上、下的留白大小

    *`spacing`: 文本行间距
    """
    with Image.new("RGBA", (1, 1), (255, 255, 255, 255)) as base:
        dr = ImageDraw.ImageDraw(base)
    ret = dr.textsize(text, font=font, spacing=spacing)
    return ret[0] + padding[0] + padding[1], ret[1] + padding[2] + padding[3]


def text_to_img(
    text: str,
    font: ImageFont.ImageFont = DEFAULTFONT,
    padding: Tuple[int, int, int, int] = (20, 20, 20, 20),
    spacing: int = 5,
) -> Image.Image:
    """
    返回一个文本转化后的`Image`实例

    *`text`：用来转图的文本

    *`font`：一个`ImageFont`实例

    *`padding`：一个四元`int`元组，分别是左、右、上、下的留白大小

    *`spacing`: 文本行间距
    """
    size = get_text_size(text, font, padding, spacing)
    base = Image.new("RGBA", size, (255, 255, 255, 255))
    dr = ImageDraw.ImageDraw(base)
    dr.text((padding[0], padding[2]), text, font=font, fill="#000000", spacing=spacing)
    return base


def img_to_bytes(pic: Image.Image) -> bytes:
    buf = BytesIO()
    pic.save(buf, format="PNG")
    return buf.getvalue()


def text_to_segment(
    text: str,
    font: ImageFont.ImageFont = DEFAULTFONT,
    padding: Tuple[int, int, int, int] = (20, 20, 20, 20),
    spacing: int = 5,
) -> MessageSegment:
    return MessageSegment.image(img_to_bytes(text_to_img(text, font, padding, spacing)))


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


def get_event_image(event: MessageEvent) -> List[str]:
    msg = event.get_message()
    imglist = [s.data["file"] for s in msg if s.type == "image" and "file" in s.data]
    return imglist


async def save_img(url: str, name: str, fav: bool = False):
    if fav:
        idir = fav_dir
    else:
        idir = img_dir
    r = await aiohttpx.get(url)
    b = BytesIO(r.content)
    img = Image.open(b).convert("RGB")
    random_modify_pixel(img)
    name = os.path.join(idir, name)
    img.save(name)
    b.close()
    img.close()

def random_modify_pixel(img:Image.Image):
    i,j = random.randint(0,img.size[0]),random.randint(0,img.size[1])
    rand_color = random.choices(range(256), k=3)
    img.putpixel((i,j),tuple(rand_color))

def get_event_imageurl(event: MessageEvent) -> List[str]:
    msg = event.message
    imglist = [s.data["url"] for s in msg if s.type == "image" and "url" in s.data]
    return imglist


async def send_to_superuser(bot: Bot, msg):
    sus = bot.config.superusers
    for su in sus:
        await bot.send_private_msg(user_id=su, message=msg)


async def get_img_from_url(url: str) -> MessageSegment:
    resp = await get(url)
    return MessageSegment.image(resp.content)

async def send(message: Union[str, "Message", "MessageSegment"],
        *,
        call_header: bool = False,
        at_sender: bool = False,
        **kwargs):
    matcher = current_matcher.get(default=None)
    if matcher is None:
        raise ValueError("No running matcher found!")
    await matcher.send(message, call_header=call_header, at_sender=at_sender, **kwargs)

async def finish(message: Union[str, "Message", "MessageSegment"],
        *,
        call_header: bool = False,
        at_sender: bool = False,
        **kwargs):
    matcher = current_matcher.get(default=None)
    if matcher is None:
        raise ValueError("No running matcher found!")
    await matcher.finish(message, call_header=call_header, at_sender=at_sender, **kwargs)