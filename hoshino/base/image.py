import asyncio
from collections.abc import Sequence
from io import BytesIO
from pathlib import Path
from time import time
from typing import Any

from httpx import URL
from nonebot.adapters import Bot, Event
from nonebot.consts import KEYWORD_KEY
from nonebot.log import logger
from nonebot.plugin import on_keyword, on_notice
from nonebot.rule import KeywordsRule, Rule
from nonebot.typing import T_State
from nonebot_plugin_alconna.uniseg import Image as UniImage
from nonebot_plugin_alconna.uniseg import UniMessage
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
    get_media_download_headers,
    get_media_url,
    get_message_id,
    get_plaintext,
    get_session_id,
    reaction_event_rule,
    redact_media_url,
    send_to_superuser,
)
from hoshino.util import aiohttpx
from hoshino.util.command import sucmd, sumsg
from hoshino.util.media import (
    SUPERUSER_IMAGE_LIST,
    SUPERUSER_VIDEO_LIST,
    get_event_image_segments,
    random_image_or_video_by_path,
    save_img,
    save_video,
)
from hoshino.util.message import (
    finish,
    send,
    send_segments,
)


async def reaction_img_rule(
    state: T_State,
    reaction: ReactionInfo | None = Reaction(),
    reacted_message: RetrievedMessage | None = ReactedMessage("66", "76", additions_only=True),
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
    state[SUPERUSER_IMAGE_LIST] = images
    state["__IMG_FAV"] = reaction.face_id == "66"
    return True


async def reaction_video_rule(
    state: T_State,
    reaction: ReactionInfo | None = Reaction(),
    reacted_message: RetrievedMessage | None = ReactedMessage("424", additions_only=True),
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
    state[SUPERUSER_VIDEO_LIST] = videos
    return True


def _media_filename(segment: Any, default: str) -> str:
    data = getattr(segment, "data", {})
    if isinstance(data, dict) and (filename := data.get("filename")):
        name = str(filename)
    else:
        name = getattr(segment, "name", None)
        if not name or name in {"image.png", "video.mp4"}:
            return default
        name = str(name)
    # 只取 basename，并拒绝 "." / ".."，防止文件名路径穿越
    basename = Path(name).name
    if basename in {"", ".", ".."}:
        return default
    return basename


async def _save_images(
    segments: Sequence[Any],
    *,
    bot: Bot,
    message_id: int,
    session_id: str,
    group_id: int | None,
    is_fav: bool,
) -> int:
    tasks = []
    dirname = str(group_id) if group_id is not None else "private"
    for index, segment in enumerate(segments):
        if not (url := await get_media_url(bot, segment)):
            continue
        default = f"{message_id}_{session_id}_{index}.jpg"
        filename = Path(dirname, _media_filename(segment, default))
        tasks.append(save_img(url, filename, is_fav, True))
    results = await asyncio.gather(*tasks, return_exceptions=True)
    saved = 0
    for result in results:
        if isinstance(result, Exception):
            logger.error(f"保存图片失败: {redact_media_url(str(result))}")
        elif result:
            saved += 1
    if saved:
        await send_to_superuser(bot, f"成功保存{saved}张图片")
    return saved


async def _save_videos(
    segments: Sequence[Any],
    *,
    bot: Bot,
    message_id: int,
    session_id: str,
) -> int:
    tasks = []
    for index, segment in enumerate(segments):
        if not (url := await get_media_url(bot, segment)):
            continue
        default = f"{message_id}_{session_id}_{index}.mp4"
        filename = _media_filename(segment, default)
        tasks.append(save_video(url, filename, True))
    results = await asyncio.gather(*tasks, return_exceptions=True)
    saved = 0
    for result in results:
        if isinstance(result, Exception):
            logger.error(f"保存视频失败: {redact_media_url(str(result))}")
        elif result:
            saved += 1
    await send_to_superuser(bot, f"成功保存{saved}视频" if saved else "保存视频失败")
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
    bot: Bot,
    event: Event,
    state: T_State,
):
    await _save_images(
        state.get(SUPERUSER_IMAGE_LIST, []),
        bot=bot,
        message_id=int(get_message_id(event, 0)),
        session_id=get_session_id(event, "unknown") or "unknown",
        group_id=get_group_id(event),
        is_fav=bool(state.get("__IMG_FAV", False) or state.get(KEYWORD_KEY, "") in {"fav", "fim"}),
    )


@svimg_notice.handle()
async def save_reaction_img_cmd(
    bot: Bot,
    state: T_State,
    reaction: ReactionInfo | None = Reaction(),
):
    if reaction is None:
        return
    await _save_images(
        state.get(SUPERUSER_IMAGE_LIST, []),
        bot=bot,
        message_id=reaction.message_id,
        session_id=f"group_{reaction.group_id}_{reaction.user_id}",
        group_id=reaction.group_id,
        is_fav=bool(state.get("__IMG_FAV", False)),
    )


@svvideo_notice.handle()
async def save_vi_cmd(
    bot: Bot,
    state: T_State,
    reaction: ReactionInfo | None = Reaction(),
):
    if reaction is None:
        return
    await _save_videos(
        state.get(SUPERUSER_VIDEO_LIST, []),
        bot=bot,
        message_id=reaction.message_id,
        session_id=f"group_{reaction.group_id}_{reaction.user_id}",
    )


async def _delete_images(names: list[str]) -> None:
    if not names:
        await finish()
    img_root = img_dir.resolve()
    fav_root = fav_dir.resolve()
    for name in names:
        img_path = (img_dir / name).resolve()
        if img_path.is_relative_to(img_root) and img_path.is_file():
            img_path.unlink()
            await send(f"删除图片{name}成功")
        fav_path = (fav_dir / name).resolve()
        if fav_path.is_relative_to(fav_root) and fav_path.is_file():
            fav_path.unlink()
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
    img_root = img_dir.resolve()
    for name in names:
        path = (img_dir / name).resolve()
        if path.is_relative_to(img_root) and path.is_file():
            # 阻塞文件读取隔离到线程，避免卡住事件循环。
            img = await asyncio.to_thread(path.read_bytes)
            await send(UniMessage.image(raw=img))
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
    segs = state[SUPERUSER_IMAGE_LIST]
    result = UniMessage()
    for seg in segs:
        url = await get_media_url(bot, seg)
        default_headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/58.0.3029.110 Safari/537.3"
            ),
        }
        if url:
            try:
                url = URL(url)
                platform_headers = await get_media_download_headers(bot, str(url))
                headers = default_headers | platform_headers
                resp = await aiohttpx.get(url, verify=True, follow_redirects=True, headers=headers)
                if resp.ok:
                    img = resp.content
                    im = Image.open(BytesIO(img))
                    im.close()
                    result += UniMessage.image(raw=img)
            except Exception:
                logger.exception(f"获取图片失败: {redact_media_url(str(url))}")
                continue
    if result:
        await finish(result)
    else:
        await timg.finish("获取图片失败")
