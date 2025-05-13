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
from nonebot.adapters.onebot.v11 import MessageSegment, Message
from nonebot.params import Depends
from nonebot.adapters.onebot.v11.event import (
    Event,
    GroupMessageEvent,
    PrivateMessageEvent,
    MessageEvent,
)
from nonebot.typing import T_State
from hoshino import fav_dir, img_dir
from nonebot.adapters.onebot.v11 import Bot
from nonebot.matcher import Matcher, current_matcher
from nonebot.permission import SUPERUSER
from nonebot.plugin import CommandGroup, on_command
from nonebot.rule import Rule, to_me
from . import aiohttpx
import json
from peewee import SqliteDatabase, Model, TextField, CompositeKey
from hoshino import db_dir


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
    return on_command(name, _depth=1, **kwargs)


def sucmds(name: str, only_to_me: bool = False, **kwargs) -> CommandGroup:
    kwargs["permission"] = SUPERUSER
    kwargs["rule"] = to_me() if only_to_me else Rule()
    handlers = kwargs.pop("handlers", [])
    handlers.insert(0, _strip_cmd)
    kwargs["handlers"] = handlers
    kwargs.setdefault("block", True)
    return CommandGroup(name, **kwargs)


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


def random_modify_pixel(img: Image.Image):
    i, j = random.randint(0, img.size[0]), random.randint(0, img.size[1])
    rand_color = random.choices(range(256), k=3)
    img.putpixel((i, j), tuple(rand_color))


def get_event_imageurl(event: MessageEvent) -> List[str]:
    msg = event.message
    imglist = [s.data.get("url", s.data.get("file")) for s in msg if s.type == "image"]
    return imglist


async def send_to_superuser(bot: Optional[Bot] = None, msg=""):
    if not bot:
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
    matcher = current_matcher.get(default=None)
    if matcher is None:
        raise ValueError("No running matcher found!")
    await matcher.send(message, call_header=call_header, at_sender=at_sender, **kwargs)


async def finish(
    message: Union[str, "Message", "MessageSegment"],
    *,
    call_header: bool = False,
    at_sender: bool = False,
    **kwargs,
):
    matcher = current_matcher.get(default=None)
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

    class Meta:
        primary_key = CompositeKey("name")
        database = db


db.connect()
db.create_tables([Cookies], safe=True)


def save_cookies(name: str, cookies: Union[str, dict]):
    if isinstance(cookies, dict):
        cookies = json.dumps(cookies)
    if isinstance(cookies, str):
        cookies = {i.split("=")[0]: i.split("=")[1] for i in cookies.split("; ")}
        cookies = json.dumps(cookies)
    Cookies.replace(name=name, cookie=cookies).execute()


def get_cookies(name: str) -> dict:
    try:
        cookie = Cookies.get(Cookies.name == name).cookie
        return json.loads(cookie)
    except Exception:
        return {}


@sucmd("save_cookies", aliases={"保存cookies", "addck", "添加cookies"}, only_to_me=True).handle()
async def save_cookies_cmd(
    event: MessageEvent,
):
    msgs = event.get_plaintext().split()
    name = msgs[0]
    cookies = msgs[1]
    if not name:
        await finish("请提供cookie名称")
    if not cookies:
        await finish("请提供cookie")

    save_cookies(name, cookies)
    await send(f"保存{name} cookies成功")
