"""事件图片 → pydantic-ai 原生多模态输入内容。

把 UniImage 段转成归一化后的 ``BinaryContent``（本地 path/raw 直接读；远程
http(s) 先抓再归一化），与文本一起作为 ``UserContent`` 序列传给同一 model。
不依赖会过期的 IM ``ImageUrl``。解析失败的段跳过并日志，不阻塞主流程。

出站图片一律规范成 JPEG/PNG（静态）或若干 JPEG 代表帧（动图）：webp/avif/bmp
等格式 provider 可能拒收，扩展名与真实格式也可能不一致，因此按字节判定并重新
编码。动图不走 ``image/gif`` 透传——OpenAI vision 只接受 non-animated GIF，直接
发送动态 GIF 会被忽略或只看第一帧，所以统一抽首/中/尾帧当多张静态图送入。
"""

from __future__ import annotations

import asyncio
from io import BytesIO
from typing import Any
from urllib.parse import urlparse

import httpx
from loguru import logger
from PIL import Image as PILImage
from pydantic_ai import BinaryContent
from pydantic_ai.messages import TextContent

from hoshino.ai.net import is_private_host

_MAX_BYTES = 15 * 1024 * 1024
_COMPRESS_THRESHOLD = 10 * 1024 * 1024
_COMPRESS_MAX = 10 * 1024 * 1024
_MAX_SIDE = 4096
_ANIMATED_MAX_SIDE = 2048
_MAX_DIMENSION = (_MAX_SIDE, _MAX_SIDE)
_ANIMATED_DIMENSION = (_ANIMATED_MAX_SIDE, _ANIMATED_MAX_SIDE)
_JPEG_QUALITY = 80
_PASSTHROUGH_FORMATS = {"JPEG": "image/jpeg", "PNG": "image/png", "GIF": "image/gif"}


def _has_alpha(image: PILImage.Image) -> bool:
    return image.mode in {"RGBA", "LA", "PA"} or (
        image.mode == "P" and "transparency" in image.info
    )


def _reencode_image(image: PILImage.Image) -> tuple[bytes, str]:
    """重新编码为 PNG（保留透明）或 JPEG；动图只保留首帧。"""
    image.seek(0)
    image.thumbnail(_MAX_DIMENSION)
    buffered = BytesIO()
    if _has_alpha(image):
        image.convert("RGBA").save(buffered, format="PNG")
        return buffered.getvalue(), "image/png"
    image.convert("RGB").save(buffered, format="JPEG", quality=_JPEG_QUALITY)
    return buffered.getvalue(), "image/jpeg"


def normalize_image_bytes(data: bytes) -> tuple[bytes, str] | None:
    """把单张静态图片规范成 JPEG/PNG/GIF，返回 ``(data, media_type)``；失败返回 None。

    已是达标格式、未超压缩阈值**且单边不超过 4096 像素**的原样返回；超阈值、超尺寸
    或其余格式（webp/avif/bmp…）重新编码：带透明通道存 PNG，否则存 JPEG（动图只留
    首帧）。动图请走 :func:`image_bytes_to_contents`，那里会抽多帧。

    尺寸必须在这里收口：长截图（群聊转发的小说截图常见 884x9644）本身是合法
    JPEG，但会超过 provider 的单边像素上限（DeepSeek 为 8192px，≥15 张图时降到
    4096px），被以「unsupported image / 格式不支持」这种误导性文案拒收。
    """
    try:
        with PILImage.open(BytesIO(data)) as image:
            media_type = _PASSTHROUGH_FORMATS.get((image.format or "").upper())
            oversized = max(image.size) > _MAX_SIDE
            if media_type and not oversized and len(data) <= _COMPRESS_THRESHOLD:
                return data, media_type
            return _reencode_image(image)
    except Exception as exc:
        logger.warning(f"AI 图片解码失败（非 JPEG/PNG/GIF）error={type(exc).__name__}")
        return None


def _content_from_bytes(data: bytes, *, origin: str) -> BinaryContent | None:
    """归一化 + 限长；不合格返回 None 并日志。"""
    if len(data) > _MAX_BYTES:
        logger.warning(f"AI 图片超过大小限制，跳过 origin={origin!r}")
        return None
    normalized = normalize_image_bytes(data)
    if normalized is None:
        logger.warning(f"AI 图片无法规范为 JPEG/PNG/GIF，跳过 origin={origin!r}")
        return None
    normalized_data, media_type = normalized
    if len(normalized_data) > _COMPRESS_MAX:
        logger.warning(f"AI 图片规范后仍超限，跳过 origin={origin!r}")
        return None
    return BinaryContent(data=normalized_data, media_type=media_type)


def _frame_to_jpeg(image: PILImage.Image, index: int) -> BinaryContent:
    """把动图第 ``index`` 帧铺白底压成 JPEG（透明通道在 JPEG 里会变黑）。"""
    image.seek(index)
    frame = image.convert("RGBA")
    frame.thumbnail(_ANIMATED_DIMENSION)
    canvas = PILImage.new("RGB", frame.size, "white")
    canvas.paste(frame, mask=frame.getchannel("A"))
    buffered = BytesIO()
    canvas.save(buffered, format="JPEG", quality=_JPEG_QUALITY)
    return BinaryContent(data=buffered.getvalue(), media_type="image/jpeg")


def _animated_frame_contents(data: bytes, *, origin: str) -> list[BinaryContent] | None:
    """动图 → 首/中/尾 3 张代表帧；静态图返回 None（交由静态路径处理）。"""
    try:
        with PILImage.open(BytesIO(data)) as image:
            if not getattr(image, "is_animated", False):
                return None
            frame_count = getattr(image, "n_frames", 1)
            # 帧数不足 3 时 set 去重后自然变少。
            frame_indices = sorted({0, frame_count // 2, frame_count - 1})
            contents = [_frame_to_jpeg(image, index) for index in frame_indices]
    except Exception as exc:
        logger.warning(
            f"AI 动图抽帧失败，按静态图处理 origin={origin!r} error={type(exc).__name__}"
        )
        return None

    kept = [content for content in contents if len(content.data) <= _COMPRESS_MAX]
    if not kept:
        logger.warning(f"AI 动图抽帧后全部超限，跳过 origin={origin!r}")
    return kept


def image_bytes_to_contents(data: bytes, *, origin: str = "bytes") -> list[BinaryContent]:
    """图片字节 → 模型输入内容：静态图 1 张，动图最多 3 张代表帧。

    动图统一抽帧而不是原样透传 ``image/gif``：OpenAI vision 只接受 non-animated
    GIF，直接发动图会被忽略或只看第一帧（见
    https://developers.openai.com/api/docs/guides/images-vision 的 File types）。
    无可用内容（超限/无法解码）返回空列表，调用方按「无图」处理。
    """
    if len(data) > _MAX_BYTES:
        logger.warning(f"AI 图片超过大小限制，跳过 origin={origin!r}")
        return []

    animated = _animated_frame_contents(data, origin=origin)
    if animated is not None:
        if animated:
            logger.info(f"AI 动图已抽帧 origin={origin!r} frames={len(animated)}")
        return animated

    content = _content_from_bytes(data, origin=origin)
    return [content] if content is not None else []


def _frame_note(contents: list[BinaryContent]) -> list[Any]:
    """多帧动图前插入一句说明，让模型知道这些图是同一动图的时间采样。"""
    if len(contents) <= 1:
        return list(contents)
    return [
        TextContent(content=f"（以下 {len(contents)} 张图是同一张动图的代表帧，按时间先后排列）"),
        *contents,
    ]


def _read_local(path: str) -> bytes | None:
    """读取本地图片字节；失败返回 None。"""
    try:
        with open(path, "rb") as f:
            return f.read()
    except OSError as exc:
        logger.warning(f"AI 图片读取失败 path={path!r} error={type(exc).__name__}")
        return None


def _local_segment_contents(segment) -> list[Any] | None:
    """本地 path/raw/file:// → 图片内容列表；无本地来源（如远程 URL）返回 None。"""
    path = getattr(segment, "path", None)
    raw = getattr(segment, "raw", None)
    url = getattr(segment, "url", "") or ""

    if isinstance(path, str) and path:
        data, origin = _read_local(path), path
    elif isinstance(raw, bytes) and raw:
        data, origin = raw, "raw"
    elif url.startswith("file://"):
        local = url.removeprefix("file://")
        data, origin = _read_local(local), local
    else:
        return None

    if data is None:
        return []
    return _frame_note(image_bytes_to_contents(data, origin=origin))


async def fetch_image_url(
    url: str,
    *,
    verify_ssl: bool = True,
    proxy: str | None = None,
) -> list[BinaryContent] | str:
    """抓取远程图片并规范为模型输入内容；动图抽帧，失败返回错误提示字符串。"""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return "仅支持 http/https 图片 URL。"

    if await is_private_host(parsed.hostname):
        return "拒绝访问私有/内网地址。"

    async with httpx.AsyncClient(
        trust_env=False,
        verify=verify_ssl,
        proxy=proxy,
        timeout=httpx.Timeout(30.0),
        follow_redirects=True,
    ) as client:
        try:
            response = await client.get(url)
            response.raise_for_status()
        except (httpx.HTTPError, ValueError) as exc:
            return f"图片抓取失败（{type(exc).__name__}）。"

    data = response.content
    if not data:
        return "图片内容为空。"
    if len(data) > _MAX_BYTES:
        return f"图片超过大小限制（{_MAX_BYTES // (1024 * 1024)}MB）。"

    contents = await asyncio.to_thread(image_bytes_to_contents, data, origin=url)
    if not contents:
        return "图片无法处理（仅支持 JPEG/PNG/GIF，处理后上限 10MB）。"
    return contents


def image_segments_to_content(segments: list) -> list[Any]:
    """同步转换本地/raw 图片段（跳过远程 URL 与解析失败的段）。"""
    parts: list[Any] = []
    for segment in segments:
        local = _local_segment_contents(segment)
        if local is not None:
            parts.extend(local)
        elif (getattr(segment, "url", "") or "").startswith(("http://", "https://")):
            logger.warning("AI 同步路径跳过远程图片（请用 image_segments_to_content_async）")
        else:
            logger.warning("AI 图片段无法解析（无可用 url/path/raw），跳过")
    return parts


async def image_segments_to_content_async(
    segments: list,
    *,
    verify_ssl: bool = True,
    proxy: str | None = None,
) -> list[Any]:
    """异步转换图片段：本地/raw 规范为模型输入内容；远程 http(s) 抓取后同样处理。"""
    parts: list[Any] = []
    for segment in segments:
        url = (getattr(segment, "url", "") or "").strip()
        local = await asyncio.to_thread(_local_segment_contents, segment)
        if local is not None:
            parts.extend(local)
            continue
        if url.startswith(("http://", "https://")):
            result = await fetch_image_url(url, verify_ssl=verify_ssl, proxy=proxy)
            if isinstance(result, list):
                parts.extend(_frame_note(result))
            else:
                logger.warning(f"AI 远程图片跳过 url={url!r} reason={result}")
            continue
        logger.warning("AI 图片段无法解析（无可用 url/path/raw），跳过")
    return parts


def build_image_prompt(prompt: str, image_parts: list[Any]) -> str | list[Any]:
    """构造多模态 UserContent：文本 + 图片；无图时回退纯文本。"""
    if not image_parts:
        return prompt
    return [TextContent(content=prompt), *image_parts]
