"""Milky message constructors for code that must explicitly target Milky."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from hoshino.platform.milky.types import Message, MessageSegment


def text_message(text: str) -> Message:
    return Message(text)


def message_from_parts(parts: Any) -> Message:
    return Message(parts)


def image_segment(file: Any) -> MessageSegment:
    if isinstance(file, str | Path):
        if str(file).startswith(("http://", "https://")):
            return MessageSegment.image(str(file))
        return MessageSegment.image(path=file)
    return MessageSegment.image(raw=file)


def video_segment(file: Any) -> MessageSegment:
    if isinstance(file, str | Path):
        if str(file).startswith(("http://", "https://")):
            return MessageSegment.video(str(file))
        return MessageSegment.video(path=file)
    return MessageSegment.video(raw=file)


def mention_segment(user_id: int) -> MessageSegment:
    return MessageSegment.mention(user_id)


def face_segment(face_id: str) -> MessageSegment:
    return MessageSegment.face(face_id)


__all__ = [
    "face_segment",
    "image_segment",
    "mention_segment",
    "message_from_parts",
    "text_message",
    "video_segment",
]
