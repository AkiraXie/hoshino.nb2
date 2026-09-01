"""事件图片 → pydantic-ai 原生多模态输入内容。

把 UniImage 段转成压缩后的 ``BinaryContent``（本地 path/raw 直接读；远程
http(s) 先抓再压），与文本一起作为 ``UserContent`` 序列传给同一 model。
不依赖会过期的 IM ``ImageUrl``。解析失败的段跳过并日志，不阻塞主流程。
"""

from __future__ import annotations

import asyncio
import mimetypes
from io import BytesIO
from typing import Any
from urllib.parse import urlparse

import httpx
from loguru import logger
from pydantic_ai import BinaryContent
from pydantic_ai.messages import TextContent

_MAX_BYTES = 15 * 1024 * 1024
_COMPRESS_THRESHOLD = 10 * 1024 * 1024
_COMPRESS_MAX = 10 * 1024 * 1024
_IMAGE_MEDIA_TYPES = ("image/png", "image/jpeg", "image/webp", "image/gif")


def _bytes_media_type(path: str) -> str:
    """按本地文件扩展名推断图片 media_type；未知按 image/png。"""
    guessed, _ = mimetypes.guess_type(path)
    if guessed and guessed.startswith("image/"):
        return guessed
    return "image/png"


def _media_type_from_content_type(content_type: str | None) -> str:
    if content_type:
        ct = content_type.split(";")[0].strip().lower()
        if ct in _IMAGE_MEDIA_TYPES:
            return ct
    return "image/png"


def _jpeg_media_if_compressed(data: bytes, fallback: str) -> str:
    return "image/jpeg" if data[:2] == b"\xff\xd8" else fallback


def compress_image_bytes(data: bytes) -> bytes:
    """把图片压缩到阈值以下（thumbnail + JPEG/80）；原图已达标则原样返回。"""
    if len(data) <= _COMPRESS_THRESHOLD:
        return data
    try:
        from PIL import Image as PILImage

        image = PILImage.open(BytesIO(data))
        image.thumbnail((4096, 4096))
        if image.mode != "RGB":
            image = image.convert("RGB")
        buffered = BytesIO()
        image.save(buffered, format="JPEG", quality=80)
        return buffered.getvalue()
    except Exception:
        return data


def _read_local(path: str) -> bytes | None:
    """读取本地图片字节并压缩；失败/超限返回 None。"""
    try:
        with open(path, "rb") as f:
            data = f.read()
    except OSError as exc:
        logger.warning(f"AI 图片读取失败 path={path!r} error={type(exc).__name__}")
        return None
    if len(data) > _MAX_BYTES:
        logger.warning(f"AI 图片超过大小限制，跳过 path={path!r}")
        return None
    data = compress_image_bytes(data)
    if len(data) > _COMPRESS_MAX:
        logger.warning(f"AI 图片压缩后仍超限，跳过 path={path!r}")
        return None
    return data


def _local_segment_to_content(segment) -> BinaryContent | None:
    """本地 path/raw/file:// → BinaryContent；远程 URL 返回 None。"""
    path = getattr(segment, "path", None)
    raw = getattr(segment, "raw", None)
    url = getattr(segment, "url", "") or ""

    if isinstance(path, str) and path:
        data = _read_local(path)
        if data is None:
            return None
        return BinaryContent(
            data=data, media_type=_jpeg_media_if_compressed(data, _bytes_media_type(path))
        )
    if isinstance(raw, bytes) and raw:
        if len(raw) > _MAX_BYTES:
            logger.warning("AI 图片超过大小限制，跳过（raw bytes）")
            return None
        data = compress_image_bytes(raw)
        if len(data) > _COMPRESS_MAX:
            logger.warning("AI 图片压缩后仍超限，跳过（raw bytes）")
            return None
        return BinaryContent(data=data, media_type=_jpeg_media_if_compressed(data, "image/png"))
    if url.startswith("file://"):
        local = url.removeprefix("file://")
        data = _read_local(local)
        if data is None:
            return None
        return BinaryContent(
            data=data, media_type=_jpeg_media_if_compressed(data, _bytes_media_type(local))
        )
    return None


async def fetch_image_url(
    url: str,
    *,
    verify_ssl: bool = True,
    proxy: str | None = None,
) -> BinaryContent | str:
    """抓取远程图片并压缩为 BinaryContent；失败返回错误提示字符串。"""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return "仅支持 http/https 图片 URL。"

    # SSRF：延迟导入避免 media→tools 循环。
    from hoshino.ai.tools.web.net import is_private_host

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

    data = await asyncio.to_thread(compress_image_bytes, data)
    if len(data) > _COMPRESS_MAX:
        return f"图片压缩后仍超过 {_COMPRESS_MAX // (1024 * 1024)}MB。"

    media = _jpeg_media_if_compressed(
        data, _media_type_from_content_type(response.headers.get("content-type"))
    )
    return BinaryContent(data=data, media_type=media)


def image_segments_to_content(segments: list) -> list[Any]:
    """同步转换本地/raw 图片段（跳过远程 URL 与解析失败的段）。"""
    parts: list[Any] = []
    for segment in segments:
        part = _local_segment_to_content(segment)
        if part is not None:
            parts.append(part)
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
    """异步转换图片段：本地/raw 压缩；远程 http(s) 抓取再压缩为 BinaryContent。"""
    parts: list[Any] = []
    for segment in segments:
        url = (getattr(segment, "url", "") or "").strip()
        local = _local_segment_to_content(segment)
        if local is not None:
            parts.append(local)
            continue
        if url.startswith(("http://", "https://")):
            result = await fetch_image_url(url, verify_ssl=verify_ssl, proxy=proxy)
            if isinstance(result, BinaryContent):
                parts.append(result)
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
