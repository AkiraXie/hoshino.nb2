import asyncio
from pathlib import Path

from nonebot import on_command
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
)
from hoshino.event import GroupReactionEvent, MessageEvent
from nonebot.plugin import on_notice
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
        if int(sender) != int(bot.self_id):
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
        url = seg.data.get("url", seg.data.get("file"))
        fname = seg.data.get("filename", name)
        url = url.replace("https://", "http://")
        try:
            await save_img(url, fname)
            cnt += 1
            await asyncio.sleep(0.2)
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
    aliases={"raimg", "randomimg"},
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
        img = MessageSegment.image(fpath)
        imgs.append(img)
    if imgs:
        names = []
        for i, name in enumerate(selected_names):
            names.append(f"{i + 1}: {name}")
        imgs.append("\n".join(names))
        await send_segments(imgs)


timg = on_command(
    "toimg",
    aliases={"转图", ".toimg"},
    rule=Rule(get_event_image_segments),
    block=False,
)


@timg.handle()
async def toimg_cmd(state: T_State):
    segs: list[MessageSegment] = state[__SU_IMGLIST]
    await timg.finish(Message(segs))
