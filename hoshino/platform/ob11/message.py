"""OB11 message construction — image_segment, video_segment, text_message, etc."""

from __future__ import annotations

from typing import Any

from hoshino.platform.ob11.types import Message, MessageSegment

MessageLike = str | Message | MessageSegment


def text_message(text: str) -> Message:
    return Message(text)


def message_from_parts(parts: Any) -> Message:
    return Message(parts)


def image_segment(file: Any) -> MessageSegment:
    return MessageSegment.image(file)


def video_segment(file: Any) -> MessageSegment:
    return MessageSegment.video(file)


def custom_node_segment(
    *,
    user_id: int,
    nickname: str,
    content: MessageLike,
) -> MessageSegment:
    """OB11 forward message node — OneBot 专有"""
    return MessageSegment.node_custom(
        user_id=user_id,
        nickname=nickname,
        content=content,
    )
