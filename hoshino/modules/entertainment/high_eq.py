'''
Author: AkiraXie
Date: 2021-02-12 01:25:05
LastEditors: AkiraXie
LastEditTime: 2021-02-12 22:35:58
Description: 
Github: http://github.com/AkiraXie/
'''
from hoshino import Service, R, Bot, MessageSegment, Event
from hoshino.util import ImageFont, Image, ImageDraw, pic2b64
from re import S
from hoshino.typing import T_State
path = R.img('high_eq_image.png')
sv = Service('high-eq', enable_on_default=False)


def draw_text(img_pil: Image.Image, text: str, offset_x: int):
    draw = ImageDraw.ImageDraw(img_pil)
    font = ImageFont.truetype(
        R.img('priconne/gadget/SourceHanSerif-Regular.ttc'), 48)
    width, height = draw.textsize(text, font)
    x = 5
    if width > 390:
        font = ImageFont.truetype(
            R.img('priconne/gadget/SourceHanSerif-Regular.ttc'), int(390 * 48 / width))
        width, height = draw.textsize(text, font)
    else:
        x = int((400 - width) / 2)
    draw.rectangle((x + offset_x - 2, 360, x + 2 + width +
                    offset_x, 360 + height * 1.2), fill=(0, 0, 0, 255))
    draw.text((x + offset_x, 360), text, font=font, fill=(255, 255, 255, 255))


@sv.on_regex(r'低情商[:：]?(.{1,15})高情商[:：]?(.{1,15})',
             flags=S, only_group=False, state={'pos': (1, 2)})
@sv.on_regex(r'高情商[:：]?(.{1,15})低情商[:：]?(.{1,15})',
             flags=S, only_group=False, state={'pos': (2, 1)})
async def _(bot: Bot, event: Event, state: T_State):
    match = state['match']
    p1, p2 = state['pos']
    low = match.group(p1).strip().strip("。").strip(".")
    high = match.group(p2).strip().strip("。").strip(".")
    img_p = Image.open(path)
    draw_text(img_p, low, 0)
    draw_text(img_p, high, 400)
    await bot.send(event, MessageSegment.image(pic2b64(img_p)))
