from hoshino.util import img_to_bytes, aiohttpx, Image, ImageDraw, BytesIO, os
from hoshino import R, MessageSegment
import random

base_path = R.img("throwandcreep/")


def get_circle_avatar(avatar: Image.Image, size: int):
    avatar = avatar.resize((size, size))
    scale = 5
    mask = Image.new("L", (size * scale, size * scale), 0)
    draw = ImageDraw.ImageDraw(mask)
    draw.ellipse((0, 0, size * scale, size * scale), fill=255)
    mask = mask.resize((size, size), Image.ANTIALIAS)
    ret_img = avatar.copy()
    ret_img.putalpha(mask)
    return ret_img


async def throw(qq: int):
    avatar_url = f"http://q1.qlogo.cn/g?b=qq&nk={qq}&s=640"
    imgres = await aiohttpx.get(avatar_url)
    if not imgres or not imgres.ok:
        return -1
    avatar = Image.open(BytesIO(imgres.content)).convert("RGBA")
    avatar = get_circle_avatar(avatar, 139)
    randomangle = random.randrange(360)
    throw_img = Image.open(base_path("throw.jpg"))
    throw_img.paste(avatar.rotate(randomangle), (17, 180), avatar.rotate(randomangle))
    throw_img = img_to_bytes(throw_img)
    throw_img = MessageSegment.image(throw_img)
    return throw_img


async def creep(qq: int):
    cid = random.randint(0, 53)
    avatar_url = f"http://q1.qlogo.cn/g?b=qq&nk={qq}&s=640"
    imgres = await aiohttpx.get(avatar_url)
    if not imgres or not imgres.ok:
        return -1
    avatar = Image.open(BytesIO(imgres.content)).convert("RGBA")
    avatar = get_circle_avatar(avatar, 100)
    creep_img = Image.open(base_path("pa", f"爬{cid}.jpg")).convert("RGBA")
    creep_img = creep_img.resize((500, 500), Image.ANTIALIAS)
    creep_img.paste(avatar, (0, 400, 100, 500), avatar)
    creep_img = img_to_bytes(creep_img)
    creep_img = MessageSegment.image(creep_img)
    return creep_img
