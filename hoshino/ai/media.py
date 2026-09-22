"""事件图片 → pydantic-ai 原生多模态输入内容。

把 UniImage 段转成归一化后的 ``BinaryContent``（本地 path/raw 直接读；远程
http(s) 先抓再归一化），与文本一起作为 ``UserContent`` 序列传给同一 model。
不依赖会过期的 IM ``ImageUrl``。解析失败的段跳过并日志，不阻塞主流程。

出站图片一律规范成 JPEG/PNG/GIF：webp/avif/bmp 等格式 provider 可能拒收，
扩展名与真实格式也可能不一致，因此按字节判定并重新编码。
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
_MAX_DIMENSION = (4096, 4096)
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
    """把图片规范成 JPEG/PNG/GIF，返回 ``(data, media_type)``；无法解码返回 None。

    已是达标格式且未超压缩阈值的原样返回（保留动图）；其余格式（webp/avif/bmp…）
    或超阈值图片重新编码：带透明通道存 PNG，否则存 JPEG（动图只留首帧，多数
    provider 也只读首帧）。
    """
    try:
        with PILImage.open(BytesIO(data)) as image:
            media_type = _PASSTHROUGH_FORMATS.get((image.format or "").upper())
            if media_type and len(data) <= _COMPRESS_THRESHOLD:
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


def _read_local(path: str) -> bytes | None:
    """读取本地图片字节；失败返回 None。"""
    try:
        with open(path, "rb") as f:
            return f.read()
    except OSError as exc:
        logger.warning(f"AI 图片读取失败 path={path!r} error={type(exc).__name__}")
        return None


def _local_segment_to_content(segment) -> BinaryContent | None:
    """本地 path/raw/file:// → BinaryContent；远程 URL 返回 None。"""
    path = getattr(segment, "path", None)
    raw = getattr(segment, "raw", None)
    url = getattr(segment, "url", "") or ""

    if isinstance(path, str) and path:
        data = _read_local(path)
        if data is None:
            return None
        return _content_from_bytes(data, origin=path)
    if isinstance(raw, bytes) and raw:
        return _content_from_bytes(raw, origin="raw")
    if url.startswith("file://"):
        local = url.removeprefix("file://")
        data = _read_local(local)
        if data is None:
            return None
        return _content_from_bytes(data, origin=local)
    return None


async def fetch_image_url(
    url: str,
    *,
    verify_ssl: bool = True,
    proxy: str | None = None,
) -> BinaryContent | str:
    """抓取远程图片并规范为 JPEG/PNG/GIF 的 BinaryContent；失败返回错误提示字符串。"""
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

    normalized = await asyncio.to_thread(normalize_image_bytes, data)
    if normalized is None:
        return "图片格式不受支持（仅 JPEG/PNG/GIF）。"
    normalized_data, media_type = normalized
    if len(normalized_data) > _COMPRESS_MAX:
        return f"图片处理后仍超过 {_COMPRESS_MAX // (1024 * 1024)}MB。"

    return BinaryContent(data=normalized_data, media_type=media_type)


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
    """异步转换图片段：本地/raw 规范为 JPEG/PNG/GIF；远程 http(s) 抓取后同样规范。"""
    parts: list[Any] = []
    for segment in segments:
        url = (getattr(segment, "url", "") or "").strip()
        local = await asyncio.to_thread(_local_segment_to_content, segment)
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
