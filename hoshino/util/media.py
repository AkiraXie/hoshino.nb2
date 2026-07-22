"""Adapter-neutral media collection and local media file helpers."""

from __future__ import annotations

import random
from collections.abc import Mapping
from io import BytesIO
from pathlib import Path
from typing import Any

from nonebot.adapters import Bot, Event
from nonebot.log import logger
from nonebot.typing import T_State
from nonebot_plugin_alconna.uniseg import Image as UniImage
from nonebot_plugin_alconna.uniseg import UniMessage
from nonebot_plugin_alconna.uniseg import Video as UniVideo
from PIL import Image

from hoshino import fav_dir, img_dir, video_dir
from hoshino.platform import (
    get_event_message,
    get_forwarded_messages,
    get_reply_message,
    to_unimessage,
)
from hoshino.types import MessageLike

from . import aiohttpx

SUPERUSER_IMAGE_LIST = "__superuser__imglist"
SUPERUSER_VIDEO_LIST = "__superuser__videolist"


async def _media_segments(
    message: Any,
    segment_type: type[UniImage] | type[UniVideo],
    *,
    bot: Bot,
    event: Event,
) -> list[UniImage | UniVideo]:
    if message is None:
        return []
    converted = await to_unimessage(message, bot=bot, event=event)
    return [segment for segment in converted if isinstance(segment, segment_type)]


async def get_event_media_segments(
    bot: Bot,
    event: Event,
    segment_type: type[UniImage] | type[UniVideo],
) -> list[UniImage | UniVideo]:
    messages = [get_event_message(event), get_reply_message(event)]
    messages.extend(await get_forwarded_messages(bot, event))
    segments = []
    seen = set()
    for message in messages:
        for segment in await _media_segments(
            message,
            segment_type,
            bot=bot,
            event=event,
        ):
            identity = (
                type(segment),
                str(getattr(segment, "url", None)),
                str(getattr(segment, "path", None)),
                str(getattr(segment, "id", None)),
                hash(raw)
                if isinstance((raw := getattr(segment, "raw", None)), bytes)
                else None,
            )
            if identity not in seen:
                seen.add(identity)
                segments.append(segment)
    return segments


async def get_event_image_segments(bot: Bot, event: Event, state: T_State) -> bool:
    images = await get_event_media_segments(bot, event, UniImage)
    if not images:
        return False
    state[SUPERUSER_IMAGE_LIST] = images
    return True


async def get_event_video_segments(bot: Bot, event: Event, state: T_State) -> bool:
    videos = await get_event_media_segments(bot, event, UniVideo)
    if not videos:
        return False
    state[SUPERUSER_VIDEO_LIST] = videos
    return True


async def save_img(
    url: str,
    name: str | Path,
    fav: bool = False,
    verify: bool = False,
) -> bool:
    image_path = (fav_dir if fav else img_dir) / name
    return await save_img_by_path(url, image_path, verify=verify) is not None


async def save_video(url: str, name: str, verify: bool = False) -> bool:
    return await save_video_by_path(url, video_dir / name, verify=verify) is not None


async def save_img_by_path(
    url: str,
    path: str | Path,
    verify: bool = False,
    headers: Mapping[str, Any] | None = None,
) -> Path | None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    response = await aiohttpx.get(
        url,
        verify=verify,
        headers=headers or {},
        follow_redirects=True,
    )
    try:
        with BytesIO(response.content) as buffer, Image.open(buffer) as image:
            if image.format:
                extension = image.format.lower()
                path = path.with_suffix(
                    f".{('jpg' if extension == 'jpeg' else extension)}"
                )
            if image.format in {"GIF", "WEBP"} and getattr(image, "is_animated", False):
                path.write_bytes(response.content)
            else:
                image.save(path)
        return path
    except Exception as error:
        logger.error("保存图片失败: {}", error)
        return None


async def save_video_by_path(
    url: str,
    path: str | Path,
    verify: bool = False,
    headers: Mapping[str, Any] | None = None,
) -> Path | None:
    response = await aiohttpx.get(
        url,
        verify=verify,
        headers=headers or {},
        follow_redirects=True,
    )
    response.raise_for_status()
    content = response.content
    if len(content) < 200:
        logger.error("视频文件过小，可能无效: {}", url)
        return None

    signatures = {
        b"\x00\x00\x00\x18ftypmp4": "mp4",
        b"\x1aE\xdf\xa3": "mkv",
        b"FLV": "flv",
        b"GIF": "gif",
        b"RIFF": "avi",
        b"ftypqt": "mov",
        b"moov": "mov",
    }
    video_format = next(
        (
            extension
            for signature, extension in signatures.items()
            if content.startswith(signature)
        ),
        None,
    )
    if video_format is None and any(
        marker in content[:50] for marker in (b"ftyp", b"moov", b"mdat")
    ):
        video_format = "mp4"
    if video_format is None:
        logger.error("下载的文件不是视频格式")
        return None

    output_path = Path(path).with_suffix(f".{video_format}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(content)
    return output_path


def random_image_or_video_by_path(
    path: Path = img_dir,
    num: int = 12,
    seed: int | None = None,
    video: bool = False,
    keyword: str | None = None,
) -> list[MessageLike]:
    names = [
        file_path.name
        for file_path in path.iterdir()
        if file_path.is_file()
        and (keyword is None or keyword.lower() in file_path.name.lower())
    ]
    if not names:
        return []

    selected_names = random.Random(seed).sample(names, k=min(len(names), num))
    media = [
        UniMessage.video(path=path / name)
        if video
        else UniMessage.image(path=path / name)
        for name in selected_names
    ]
    media.append(
        "\n".join(f"{index}: {name}" for index, name in enumerate(selected_names, 1))
    )
    return media


__all__ = [
    "SUPERUSER_IMAGE_LIST",
    "SUPERUSER_VIDEO_LIST",
    "get_event_image_segments",
    "get_event_media_segments",
    "get_event_video_segments",
    "random_image_or_video_by_path",
    "save_img",
    "save_img_by_path",
    "save_video",
    "save_video_by_path",
]
