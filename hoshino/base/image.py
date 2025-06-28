import asyncio
from io import BytesIO
from PIL import Image
from pathlib import Path
from hoshino import (
    Message,
    Bot,
    T_State,
    SUPERUSER,
    MessageSegment,
    img_dir,
    fav_dir,
    video_dir,
)
from hoshino.util import (
    __SU_IMGLIST,
    __SU_VIDEOLIST,
    save_img,
    sucmd,
    finish,
    send,
    send_segments,
    get_event_image_segments,
    send_to_superuser,
    _get_imgs_from_forward_msg,
    _get_videos_from_forward_msg,
    aiohttpx,
    sumsg,
    save_video,
    random_image_or_video_by_path
)
from hoshino.event import GroupReactionEvent, MessageEvent
from nonebot.plugin import on_notice, on_keyword
from nonebot.rule import Rule, KeywordsRule
from nonebot.compat import type_validate_python
from nonebot.log import logger
from nonebot.consts import KEYWORD_KEY
import os
import random
from time import time
from httpx import URL


async def reaction_img_rule(
    bot: Bot,
    event: GroupReactionEvent,
    state: T_State,
) -> bool:
    if event.code != "76" and event.code != "66":
        return False
    msg_id = event.message_id
    msg = await bot.get_msg(message_id=msg_id)
    sender = msg.get("sender", {}).get("user_id")
    sender = str(sender)
    if sender != bot.self_id and sender not in bot.config.superusers:
        return False
    msg = msg.get("message")
    if msg:
        msg = type_validate_python(Message, msg)
        img_list = [s for s in msg if s.type == "image"]
        img_list.extend(await _get_imgs_from_forward_msg(bot, msg))
        if img_list:
            state[__SU_IMGLIST] = img_list
            state["__IMG_FAV"] = True if event.code == "66" else False
            return True
    return False


async def reaction_video_rule(
    bot: Bot,
    event: GroupReactionEvent,
    state: T_State,
) -> bool:
    msg_id = event.message_id
    msg = await bot.get_msg(message_id=msg_id)
    sender = msg.get("sender", {}).get("user_id")
    sender = str(sender)
    if sender != bot.self_id and sender not in bot.config.superusers:
        return False
    msg = msg.get("message")
    if event.code == "424":
        if msg:
            msg = type_validate_python(Message, msg)
            img_list = [s for s in msg if s.type == "video"]
            img_list.extend(await _get_videos_from_forward_msg(bot, msg))
            if img_list:
                state[__SU_VIDEOLIST] = img_list
                return True
    return False


svimg_notice = on_notice(
    rule=reaction_img_rule,
    permission=SUPERUSER,
    priority=5,
    block=True,
)
svvideo_notice = on_notice(
    rule=reaction_video_rule,
    permission=SUPERUSER,
    priority=5,
    block=True,
)


@sumsg(
    only_to_me=True,
    rule=Rule(get_event_image_segments)
    & KeywordsRule("sim", "存图", "saveimg", "ctu", "fav", "fim"),
).handle()
@svimg_notice.handle()
async def save_img_cmd(event: MessageEvent | GroupReactionEvent, state: T_State):
    segs: list[MessageSegment] = state.get(__SU_IMGLIST, [])
    cnt = 0
    tasks = []
    is_fav = (
        True
        if state.get("__IMG_FAV", False) or state.get(KEYWORD_KEY, "") in ("fav", "fim")
        else False
    )
    for i, seg in enumerate(segs):
        name = f"{event.message_id}_{event.get_session_id()}_{i}.jpg"
        url = seg.data.get("file", seg.data.get("url"))
        fname = seg.data.get("filename", name)
        url = url.replace("https://", "http://")
        tasks.append(save_img(url, fname, is_fav, False))
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for result in results:
        if isinstance(result, Exception):
            logger.exception(f"保存图片失败: {result}")
        elif result:
            cnt += 1
    if cnt != 0:
        await send_to_superuser(f"成功保存{cnt}张图片")
    else:
        await send_to_superuser("保存图片失败")


@svvideo_notice.handle()
async def save_vi_cmd(event: GroupReactionEvent, state: T_State):
    segs: list[MessageSegment] = state.get(__SU_VIDEOLIST, [])
    cnt = 0
    tasks = []
    for i, seg in enumerate(segs):
        name = f"{event.message_id}_{event.get_session_id()}_{i}.mp4"
        url = seg.data.get("file", seg.data.get("url"))
        fname = seg.data.get("filename", name)
        url = url.replace("https://", "http://")
        tasks.append(save_video(url, fname, False))
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for result in results:
        if isinstance(result, Exception):
            logger.exception(f"保存视频失败: {result}")
        elif result:
            cnt += 1
    if cnt != 0:
        await send_to_superuser(f"成功保存{cnt}视频")
    else:
        await send_to_superuser("保存视频失败")


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
        path = os.path.join(fav_dir, name)
        if os.path.exists(path):
            os.remove(path)
            await send(f"删除收藏图片{name}成功")


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
    aliases={"raimg", "randomimg", "rim"},
    only_to_me=True,
).handle()
async def random_img_cmd(
    event: MessageEvent,
):
    path = img_dir
    num = 12
    if event.get_plaintext().isdigit():
        num = int(event.get_plaintext())
    seed = time() + event.message_id
    imgs = random_image_or_video_by_path(
        path,
        num=num,
        seed=seed,
    )
    await send_segments(imgs)


@sucmd(
    "随收",
    aliases={"rafav", "randomfav", "rfa"},
    only_to_me=True,
).handle()
async def random_fav_cmd(
    event: MessageEvent,
):
    path = fav_dir
    num = 12
    if event.get_plaintext().isdigit():
        num = int(event.get_plaintext())
    seed = time() + event.message_id
    imgs = random_image_or_video_by_path(
        path,
        num=num,
        seed=seed,
    )
    await send_segments(imgs)
@sucmd(
    "随影",
    aliases={"rvi", "rav"},
    only_to_me=True,
).handle()
async def random_vi_cmd(
    event: MessageEvent,
):
    path = video_dir
    num = 3
    if event.get_plaintext().isdigit():
        num = int(event.get_plaintext())
    seed = time() + event.message_id
    imgs = random_image_or_video_by_path(
        path,
        num=num,
        seed=seed,
        video=True,
    )
    await send_segments(imgs)


timg = on_keyword(
    {".toimg", "/toimg"},
    rule=Rule(get_event_image_segments),
    block=False,
)


@timg.handle()
async def toimg_cmd(bot: Bot, state: T_State):
    segs: list[MessageSegment] = state[__SU_IMGLIST]
    res = []
    for seg in segs:
        url = seg.data.get("url", seg.data.get("file"))
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3",
        }
        if url:
            url = url.replace("https://", "http://")
            try:
                url = URL(url)
                domain = url.host
                try:
                    if "vip.qq.com" in domain:
                        domain = "vip.qq.com"
                        ck = await bot.get_cookies(domain=domain)
                        ck = ck.get("cookies")
                        if ck:
                            headers = {
                                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3",
                                "cookies": ck,
                            }
                except Exception as e:
                    logger.exception(f"获取 cookies 失败: {e}")
                resp = await aiohttpx.get(
                    url, verify=False, follow_redirects=True, headers=headers
                )
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
    else:
        await timg.finish("获取图片失败")
