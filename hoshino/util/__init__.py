'''
Author: AkiraXie
Date: 2021-01-28 14:29:01
LastEditors: AkiraXie
LastEditTime: 2021-01-29 23:26:49
Description: 
Github: http://github.com/AkiraXie/
'''
from typing import ItemsView, Iterable, Optional, Tuple
from io import BytesIO
from collections import defaultdict
from PIL import Image, ImageDraw, ImageFont
from datetime import datetime, timedelta
from loguru import logger
import os
import json
import unicodedata
import time
import pytz
import base64
import zhconv
import nonebot
from nonebot.adapters.cqhttp import Bot
from nonebot.matcher import Matcher
from nonebot.permission import SUPERUSER
from nonebot.plugin import on_command
from nonebot.rule import Rule


class FreqLimiter:
    def __init__(self, default_cd_seconds):
        self.next_time = defaultdict(float)
        self.default_cd = default_cd_seconds

    def check(self, key) -> bool:
        return bool(time.time() >= self.next_time[key])

    def start_cd(self, key, cd_time=0):
        self.next_time[key] = time.time(
        ) + cd_time if cd_time > 0 else self.default_cd


class DailyNumberLimiter:
    tz = pytz.timezone('Asia/Shanghai')

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


def load_config(inbuilt_file_var):
    """
    Just use `config = load_config(__file__)`,
    you can get the config.json as a dict.
    """
    filename = os.path.join(os.path.dirname(inbuilt_file_var), 'config.json')
    try:
        with open(filename, encoding='utf8') as f:
            config = json.load(f)
            return config
    except Exception as e:
        logger.exception(e)
        return {}


def get_bot_list() -> ItemsView[str, Bot]:
    return nonebot.get_bots().items()


def sucmd(name: str, rule: Rule = Rule(), aliases: Optional[Iterable] = None, **kwargs) -> Matcher:
    kwargs['aliases'] = aliases
    kwargs['permission'] = SUPERUSER
    kwargs['rule'] = rule
    return on_command(name, **kwargs)


def get_text_size(text: str, font: ImageFont.ImageFont, padding: Tuple[int, int, int, int] = (20, 20, 20, 20), spacing: int = 5) -> tuple:
    '''
    返回文本转图片的图片大小

    *`text`：用来转图的文本
    *`font`：一个`ImageFont`实例
    *`padding`：一个四元`int`元组，分别是左、右、上、下的留白大小
    *`spacing`: 文本行间距
    '''
    with Image.new('RGBA', (1, 1), (255, 255, 255, 255)) as base:
        dr = ImageDraw.ImageDraw(base)
    ret = dr.textsize(text, font=font, spacing=spacing)
    return ret[0]+padding[0]+padding[1], ret[1]+padding[2]+padding[3]


def text2pic(text: str, font: ImageFont.ImageFont, padding: Tuple[int, int, int, int] = (20, 20, 20, 20), spacing: int = 5) -> Image.Image:
    '''
    返回一个文本转化后的`Image`实例

    *`text`：用来转图的文本
    *`font`：一个`ImageFont`实例
    *`padding`：一个四元`int`元组，分别是左、右、上、下的留白大小
    *`spacing`: 文本行间距
    '''
    size = get_text_size(text, font, padding, spacing)
    base = Image.new('RGBA', size, (255, 255, 255, 255))
    dr = ImageDraw.ImageDraw(base)
    dr.text((padding[0], padding[2]), text, font=font,
            fill='#000000', spacing=spacing)
    return base


def pic2b64(pic: Image.Image) -> str:
    buf = BytesIO()
    pic.save(buf, format='PNG')
    base64_str = base64.b64encode(
        buf.getvalue()).decode()  # , encoding='utf8')
    return 'base64://' + base64_str


def concat_pic(pics, border=5):
    num = len(pics)
    w, h = pics[0].size
    des = Image.new('RGBA', (w, num * h + (num-1) * border),
                    (255, 255, 255, 255))
    for i, pic in enumerate(pics):
        des.paste(pic, (0, i * (h + border)), pic)
    return des


def normalize_str(string) -> str:
    """
    规范化unicode字符串 并 转为小写 并 转为简体
    """
    string = unicodedata.normalize('NFKC', string)
    string = string.lower()
    string = zhconv.convert(string, 'zh-hans')
    return string
