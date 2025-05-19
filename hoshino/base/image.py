import asyncio
from io import BytesIO
from PIL import Image
from pathlib import Path
from hoshino import Message, Bot, T_State, SUPERUSER, MessageSegment, img_dir
from hoshino.util import (
    __SU_IMGLIST,
    save_img,
    sucmd,
    sumsg,
    finish,
    send,
    send_segments,
    get_event_image_segments,
    send_to_superuser,
    _get_imgs_from_forward_msg,
    aiohttpx,
)
from hoshino.event import GroupReactionEvent, MessageEvent
from nonebot.plugin import on_notice, on_keyword
from nonebot.rule import Rule, KeywordsRule
from nonebot.compat import type_validate_python
from nonebot.log import logger
import os
import random
from time import time


async def reaction_img_rule(
    bot: Bot,
    event: GroupReactionEvent,
    state: T_State,
) -> bool:
    if event.code == "76":
        msg_id = event.message_id
        msg = await bot.get_msg(message_id=msg_id)
        sender = msg.get("sender", {}).get("user_id")
        if sender != bot.self_id and sender not in bot.config.superusers:
            return False
        msg = msg.get("message")
        if msg:
            msg = type_validate_python(Message, msg)
            img_list = [s for s in msg if s.type == "image"]
            img_list.extend(await _get_imgs_from_forward_msg(bot, msg))
            if img_list:
                state[__SU_IMGLIST] = img_list
                return True
    return False


svimg_notice = on_notice(
    rule=reaction_img_rule,
    permission=SUPERUSER,
    priority=5,
    block=True,
)


@sumsg(
    only_to_me=True,
    rule=Rule(get_event_image_segments) & KeywordsRule("sim", "存图", "saveimg", "ctu"),
).handle()
@svimg_notice.handle()
async def save_img_cmd(event: MessageEvent | GroupReactionEvent, state: T_State):
    segs: list[MessageSegment] = state[__SU_IMGLIST]
    cnt = 0
    for i, seg in enumerate(segs):
        name = f"{event.message_id}_{event.get_session_id()}_{i}"
        url = seg.data.get("file", seg.data.get("url"))
        fname = seg.data.get("filename", name)
        url = url.replace("https://", "http://")
        try:
            res = await save_img(url, fname)
            if res:
                cnt += 1
                await asyncio.sleep(0.2)
            else:
                logger.exception(f"保存图片失败: {fname}")
                continue
        except Exception:
            logger.exception(f"保存图片失败: {fname}")
            continue
    if cnt != 0:
        await send_to_superuser(f"成功保存{cnt}张图片")
    else:
        await send_to_superuser("保存图片失败")


@sucmd(
    "删图",
    aliases={"st", "rmimg", "delimg", "deleteimg"},
    only_to_me=True,
).handle()
async def delete_img_cmd(
    event: MessageEvent,
):
    names = event.get_plaintext().split(None)
    if not names:
        await finish()
    for name in names:
        path = os.path.join(img_dir, name)
        if os.path.exists(path):
            os.remove(path)
            await send(f"删除图片{name}成功")


@sucmd(
    "看图",
    aliases={"kt", "kkimg", "showimg", "showimage"},
    only_to_me=True,
).handle()
async def show_img_cmd(
    event: MessageEvent,
):
    names = event.get_plaintext().split(None)
    if not names:
        await finish()
    for name in names:
        path = os.path.join(img_dir, name)
        if os.path.exists(path):
            with open(path, "rb") as f:
                img = f.read()
                await send(MessageSegment.image(img))
        else:
            await send(f"图片{name}不存在")


@sucmd(
    "随图",
    aliases={"raimg", "randomimg", "rimg"},
    only_to_me=True,
).handle()
async def random_img_cmd(
    event: MessageEvent,
):
    path = img_dir
    names = os.listdir(path)
    if not names:
        await finish()
    num = min(len(names), 5)
    imgs = []
    ra = random.SystemRandom(time() + event.message_id)
    selected_names = ra.sample(names, k=num)
    for name in selected_names:
        fpath = os.path.join(path, name)
        fpath = Path(fpath)
        try:
            im = Image.open(fpath)
            img = MessageSegment.image(fpath)
            imgs.append(img)
            im.close()
        except Exception:
            logger.exception(f"打开图片失败: {fpath}")
            os.remove(fpath)
            continue
    if imgs:
        names = []
        for i, name in enumerate(selected_names):
            names.append(f"{i + 1}: {name}")
        imgs.append("\n".join(names))
        await send_segments(imgs)


@sucmd(
    "全图",
    aliases={"aimg", "allimg", "qt"},
    only_to_me=True,
).handle()
async def all_img_cmd(
    event: MessageEvent,
):
    path = img_dir
    names = os.listdir(path)
    if not names:
        await finish()
    imgs = []
    ns = []
    for name in names:
        fpath = os.path.join(path, name)
        fpath = Path(fpath)
        try:
            im = Image.open(fpath)
            img = MessageSegment.image(fpath)
            imgs.append(img)
            ns.append(name)
            im.close()
        except Exception:
            logger.exception(f"打开图片失败: {fpath}")
            os.remove(fpath)
            continue
    if imgs:
        n = 9
        await send(f"共{len(imgs)}张图片")
        for i in range(0, len(imgs), n):
            await asyncio.sleep(1)
            chunk = imgs[i : i + n]
            chunk.append(f"第{i + 1}-{min(i + n, len(imgs))}张")
            chunk.append("\n".join(ns[i : i + n]))
            await send_segments(chunk)


timg = on_keyword(
    {".toimg", "/toimg"},
    rule=Rule(get_event_image_segments),
    block=False,
)


@timg.handle()
async def toimg_cmd(state: T_State):
    segs: list[MessageSegment] = state[__SU_IMGLIST]
    res = []
    for seg in segs:
        url = seg.data.get("url", seg.data.get("file"))
        if url:
            url = url.replace("https://", "http://")
            try:
                resp = await aiohttpx.get(url, verify=False, follow_redirects=True)
                if resp.ok:
                    img = resp.content
                    im = Image.open(BytesIO(img))
                    im.close()
                    res.append(MessageSegment.image(img))
            except Exception:
                logger.exception(f"获取图片失败: {url}")
                continue
    if res:
        await timg.finish(Message(res))
