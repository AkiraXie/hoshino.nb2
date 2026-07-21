import asyncio
import os
from io import BytesIO
from pathlib import Path
from time import time
from typing import Any, Sequence

from httpx import URL
from nonebot.adapters import Bot, Event
from nonebot.consts import KEYWORD_KEY
from nonebot.log import logger
from nonebot.plugin import on_keyword, on_notice
from nonebot.rule import KeywordsRule, Rule
from nonebot.typing import T_State
from nonebot_plugin_alconna.uniseg import Image as UniImage
from nonebot_plugin_alconna.uniseg import Video as UniVideo
from PIL import Image

from hoshino import fav_dir, img_dir, video_dir
from hoshino.core.permission import SUPERUSER
from hoshino.platform import (
    ReactedMessage,
    Reaction,
    ReactionInfo,
    RetrievedMessage,
    get_group_id,
    get_message_id,
    get_plaintext,
    get_session_id,
    image_segment,
    reaction_event_rule,
)
from hoshino.platform.ob11.types import OneBotV11Message
from hoshino.util import (
    __SU_IMGLIST,
    __SU_VIDEOLIST,
    aiohttpx,
    finish,
    get_event_image_segments,
    random_image_or_video_by_path,
    save_img,
    save_video,
    send,
    send_segments,
    send_to_superuser,
    sucmd,
    sumsg,
)


async def reaction_img_rule(
    state: T_State,
    reaction: ReactionInfo | None = Reaction(),
    reacted_message: RetrievedMessage | None = ReactedMessage(
        "66", "76", additions_only=True
    ),
) -> bool:
    if (
        reaction is None
        or reacted_message is None
        or not reaction.is_add
        or reaction.face_id not in {"66", "76"}
        or not reacted_message.trusted_sender
    ):
        return False
    images = [
        segment
        for message in reacted_message.messages
        for segment in message
        if isinstance(segment, UniImage)
    ]
    if not images:
        return False
    state[__SU_IMGLIST] = images
    state["__IMG_FAV"] = reaction.face_id == "66"
    return True


async def reaction_video_rule(
    state: T_State,
    reaction: ReactionInfo | None = Reaction(),
    reacted_message: RetrievedMessage | None = ReactedMessage(
        "424", additions_only=True
    ),
) -> bool:
    if (
        reaction is None
        or reacted_message is None
        or not reaction.is_add
        or reaction.face_id != "424"
        or not reacted_message.trusted_sender
    ):
        return False
    videos = [
        segment
        for message in reacted_message.messages
        for segment in message
        if isinstance(segment, UniVideo)
    ]
    if not videos:
        return False
    state[__SU_VIDEOLIST] = videos
    return True


def _media_url(segment: Any) -> str | None:
    if url := getattr(segment, "url", None):
        return str(url)
    data = getattr(segment, "data", {})
    if not isinstance(data, dict):
        return None
    for key in ("url", "file", "temp_url", "uri"):
        if value := data.get(key):
            return str(value)
    return None


def _media_filename(segment: Any, default: str) -> str:
    data = getattr(segment, "data", {})
    if isinstance(data, dict) and (filename := data.get("filename")):
        return str(filename)
    name = getattr(segment, "name", None)
    if name and name not in {"image.png", "video.mp4"}:
        return str(name)
    return default


async def _save_images(
    segments: Sequence[Any],
    *,
    message_id: int,
    session_id: str,
    group_id: int | None,
    is_fav: bool,
) -> int:
    tasks = []
    dirname = str(group_id) if group_id is not None else "private"
    for index, segment in enumerate(segments):
        if not (url := _media_url(segment)):
            continue
        default = f"{message_id}_{session_id}_{index}.jpg"
        filename = Path(dirname, _media_filename(segment, default))
        tasks.append(
            save_img(url.replace("https://", "http://"), filename, is_fav, False)
        )
    results = await asyncio.gather(*tasks, return_exceptions=True)
    saved = 0
    for result in results:
        if isinstance(result, Exception):
            logger.error(f"保存图片失败: {result}")
        elif result:
            saved += 1
    if saved:
        await send_to_superuser(f"成功保存{saved}张图片")
    return saved


async def _save_videos(
    segments: Sequence[Any],
    *,
    message_id: int,
    session_id: str,
) -> int:
    tasks = []
    for index, segment in enumerate(segments):
        if not (url := _media_url(segment)):
            continue
        default = f"{message_id}_{session_id}_{index}.mp4"
        filename = _media_filename(segment, default)
        tasks.append(save_video(url.replace("https://", "http://"), filename, False))
    results = await asyncio.gather(*tasks, return_exceptions=True)
    saved = 0
    for result in results:
        if isinstance(result, Exception):
            logger.error(f"保存视频失败: {result}")
        elif result:
            saved += 1
    await send_to_superuser(f"成功保存{saved}视频" if saved else "保存视频失败")
    return saved


svimg_notice = on_notice(
    rule=reaction_event_rule & Rule(reaction_img_rule),
    permission=SUPERUSER,
    priority=5,
    block=True,
)
svvideo_notice = on_notice(
    rule=reaction_event_rule & Rule(reaction_video_rule),
    permission=SUPERUSER,
    priority=5,
    block=True,
)


@sumsg(
    only_to_me=True,
    rule=Rule(get_event_image_segments)
    & KeywordsRule("sim", "存图", "saveimg", "ctu", "fav", "fim"),
).handle()
async def save_img_cmd(
    event: Event,
    state: T_State,
):
    await _save_images(
        state.get(__SU_IMGLIST, []),
        message_id=int(get_message_id(event, 0)),
        session_id=get_session_id(event, "unknown") or "unknown",
        group_id=get_group_id(event),
        is_fav=bool(
            state.get("__IMG_FAV", False)
            or state.get(KEYWORD_KEY, "") in {"fav", "fim"}
        ),
    )


@svimg_notice.handle()
async def save_reaction_img_cmd(
    state: T_State,
    reaction: ReactionInfo | None = Reaction(),
):
    if reaction is None:
        return
    await _save_images(
        state.get(__SU_IMGLIST, []),
        message_id=reaction.message_id,
        session_id=f"group_{reaction.group_id}_{reaction.user_id}",
        group_id=reaction.group_id,
        is_fav=bool(state.get("__IMG_FAV", False)),
    )


@svvideo_notice.handle()
async def save_vi_cmd(
    state: T_State,
    reaction: ReactionInfo | None = Reaction(),
):
    if reaction is None:
        return
    await _save_videos(
        state.get(__SU_VIDEOLIST, []),
        message_id=reaction.message_id,
        session_id=f"group_{reaction.group_id}_{reaction.user_id}",
    )


async def _delete_images(names: list[str]) -> None:
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
    "删图",
    aliases={"rmimg", "delimg", "deleteimg"},
    only_to_me=True,
).handle()
async def delete_img_cmd(event: Event):
    await _delete_images(get_plaintext(event).split())


def _short_delete_rule(event: Event) -> bool:
    text = get_plaintext(event).lstrip()
    return text == "st" or (text.startswith("st") and text[2:3].isspace())


short_delete_img = sumsg(rule=Rule(_short_delete_rule))


@short_delete_img.handle()
async def short_delete_img_cmd(event: Event):
    await _delete_images(get_plaintext(event).lstrip()[2:].split())


@sucmd(
    "看图",
    aliases={"kt", "kkimg", "showimg", "showimage"},
    only_to_me=True,
).handle()
async def show_img_cmd(
    event: Event,
):
    names = get_plaintext(event).split(None)
    if not names:
        await finish()
    for name in names:
        path = os.path.join(img_dir, name)
        if os.path.exists(path):
            with open(path, "rb") as f:
                img = f.read()
                await send(image_segment(img))
        else:
            await send(f"图片{name}不存在")


@sucmd(
    "随图",
    aliases={"raimg", "randomimg", "rim"},
    only_to_me=True,
).handle()
async def random_img_cmd(
    event: Event,
):
    path = img_dir
    num = 12
    text = get_plaintext(event)
    if text.isdigit():
        num = int(text)
    seed = time() + int(get_message_id(event, 0))
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
    event: Event,
):
    path = fav_dir
    num = 12
    text = get_plaintext(event)
    if text.isdigit():
        num = int(text)
    seed = time() + int(get_message_id(event, 0))
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
    event: Event,
):
    path = video_dir
    num = 3
    text = get_plaintext(event)
    if text.isdigit():
        num = int(text)
    seed = time() + int(get_message_id(event, 0))
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
    segs = state[__SU_IMGLIST]
    res = []
    for seg in segs:
        url = _media_url(seg)
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/58.0.3029.110 Safari/537.3"
            ),
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
                                "User-Agent": (
                                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                                    "Chrome/58.0.3029.110 Safari/537.3"
                                ),
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
                    res.append(image_segment(img))
            except Exception:
                logger.exception(f"获取图片失败: {url}")
                continue
    if res:
        await finish(OneBotV11Message(res))
    else:
        await timg.finish("获取图片失败")
