"""事件图片 → pydantic-ai 多模态输入内容。

``chat`` 收到含图消息且当前 provider/scope 配置了多模态模型时，把 UniImage 段转成
``ImageUrl``（远程 http(s)）或 ``BinaryContent``（本地 path/raw 字节），与文本一起
作为 ``UserContent`` 序列传给 Agent。解析失败的段跳过并日志，不阻塞主流程。
"""

from __future__ import annotations

import mimetypes
from typing import Any

from loguru import logger
from pydantic_ai import BinaryContent, ImageUrl
from pydantic_ai.messages import TextContent

_MAX_BYTES = 15 * 1024 * 1024


def _bytes_media_type(path: str) -> str:
    """按本地文件扩展名推断图片 media_type；未知按 image/png。"""
    guessed, _ = mimetypes.guess_type(path)
    if guessed and guessed.startswith("image/"):
        return guessed
    return "image/png"


def _read_local(path: str) -> bytes | None:
    """读取本地图片字节；失败/超限返回 None。"""
    try:
        with open(path, "rb") as f:
            data = f.read()
    except OSError as exc:
        logger.warning(f"AI 图片读取失败 path={path!r} error={type(exc).__name__}")
        return None
    if len(data) > _MAX_BYTES:
        logger.warning(f"AI 图片超过大小限制，跳过 path={path!r}")
        return None
    return data


def _segment_to_content(segment) -> Any | None:
    """单个 UniImage 段 → ImageUrl / BinaryContent；无法解析返回 None。"""
    path = getattr(segment, "path", None)
    raw = getattr(segment, "raw", None)
    url = getattr(segment, "url", "") or ""

    # 本地文件优先：path 或 raw 字节 → BinaryContent（不依赖平台能外链访问）。
    if isinstance(path, str) and path:
        data = _read_local(path)
        return (
            BinaryContent(data=data, media_type=_bytes_media_type(path))
            if data is not None
            else None
        )
    if isinstance(raw, bytes) and raw:
        if len(raw) > _MAX_BYTES:
            logger.warning("AI 图片超过大小限制，跳过（raw bytes）")
            return None
        return BinaryContent(data=raw, media_type="image/png")

    # 远程 URL：http(s) 直接给 ImageUrl（模型侧下载）；OB11 file:// 转本地路径。
    if url.startswith("file://"):
        local = url.removeprefix("file://")
        data = _read_local(local)
        return (
            BinaryContent(data=data, media_type=_bytes_media_type(local))
            if data is not None
            else None
        )
    if url.startswith(("http://", "https://")):
        return ImageUrl(url=url)

    logger.warning("AI 图片段无法解析（无可用 url/path/raw），跳过")
    return None


def image_segments_to_content(segments: list) -> list[Any]:
    """把事件图片段转成 pydantic-ai 多模态内容列表（跳过解析失败的段）。"""
    parts: list[Any] = []
    for segment in segments:
        part = _segment_to_content(segment)
        if part is not None:
            parts.append(part)
    return parts


def build_multimodal_prompt(prompt: str, segments: list) -> str | list[Any]:
    """构造多模态 UserContent：文本 + 图片内容；图片全部失败时回退纯文本。"""
    content = image_segments_to_content(segments)
    if not content:
        return prompt
    return [TextContent(content=prompt), *content]
