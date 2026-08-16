"""Cross-adapter forwarded-message and media extraction coverage."""

from __future__ import annotations

from typing import Any

import pytest
from nonebot import get_driver
from nonebot.adapters.milky import Bot as MilkyBot
from nonebot.adapters.milky import Message as MilkyMessage
from nonebot.adapters.milky.model.message import IncomingForwardedMessage
from nonebot.adapters.onebot.v11 import Adapter as OB11Adapter
from nonebot.adapters.onebot.v11 import Bot as OB11Bot
from nonebot.adapters.onebot.v11 import GroupMessageEvent as OB11GroupMessageEvent
from nonebot.adapters.onebot.v11 import Message as OB11Message
from nonebot.adapters.onebot.v11 import MessageSegment as OB11Segment
from nonebot.adapters.telegram import Adapter as TelegramAdapter
from nonebot.adapters.telegram import Bot as TelegramBot
from nonebot.adapters.telegram.config import BotConfig as TelegramBotConfig
from nonebot.adapters.telegram.event import MessageEvent as TelegramMessageEvent
from nonebot_plugin_alconna.uniseg import Image, Video


def _ob11_forward_event() -> tuple[OB11Bot, OB11GroupMessageEvent]:
    bot = OB11Bot(OB11Adapter(get_driver()), self_id="10000")
    message = OB11Message(OB11Segment.forward("forward-1"))
    event = OB11GroupMessageEvent(
        time=1,
        self_id=10000,
        post_type="message",
        sub_type="normal",
        user_id=42,
        message_type="group",
        message_id=7,
        message=message,
        original_message=message,
        raw_message="[forward]",
        font=0,
        sender={"user_id": 42, "nickname": "Alice", "role": "member"},
        group_id=123456,
        to_me=False,
    )
    return bot, event


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_ob11_forwarded_messages_expose_images_and_videos(monkeypatch):
    from hoshino.platform import get_forwarded_messages
    from hoshino.util.media import get_event_media_segments

    async def fake_call_api(self, api: str, **data: Any):
        assert api == "get_forward_msg"
        assert data == {"id": "forward-1"}
        return {
            "messages": [
                {
                    "content": [
                        {
                            "type": "image",
                            "data": {
                                "file": "image.jpg",
                                "url": "https://example.com/image.jpg",
                            },
                        },
                        {
                            "type": "video",
                            "data": {
                                "file": "video.mp4",
                                "url": "https://example.com/video.mp4",
                            },
                        },
                    ]
                }
            ]
        }

    monkeypatch.setattr(OB11Bot, "call_api", fake_call_api)
    bot, event = _ob11_forward_event()

    forwarded = await get_forwarded_messages(bot, event)
    images = await get_event_media_segments(bot, event, Image)
    videos = await get_event_media_segments(bot, event, Video)

    assert len(forwarded) == 1
    assert [image.url for image in images] == ["https://example.com/image.jpg"]
    assert [video.url for video in videos] == ["https://example.com/video.mp4"]


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_milky_forwarded_messages_expose_images_and_videos(monkeypatch):
    from _helpers import _milky_group_message
    from hoshino.platform import get_forwarded_messages
    from hoshino.util.media import get_event_media_segments

    bot, event = _milky_group_message("ignored", to_me=False)
    forward_elements = [
        {
            "type": "forward",
            "data": {
                "forward_id": "forward-1",
                "title": "",
                "preview": [],
                "summary": "",
            },
        }
    ]
    event.data.segments = forward_elements
    event.message = MilkyMessage.from_elements(forward_elements)
    event.original_message = event.message

    async def fake_get_forwarded_messages(self, forward_id: str):
        assert forward_id == "forward-1"
        return [
            IncomingForwardedMessage.model_validate(
                {
                    "sender_name": "Alice",
                    "avatar_url": "https://example.com/avatar.jpg",
                    "time": 1,
                    "segments": [
                        {
                            "type": "image",
                            "data": {
                                "resource_id": "image-resource",
                                "temp_url": "https://example.com/image.jpg",
                                "width": 100,
                                "height": 100,
                                "sub_type": "normal",
                            },
                        },
                        {
                            "type": "video",
                            "data": {
                                "resource_id": "video-resource",
                                "temp_url": "https://example.com/video.mp4",
                                "width": 100,
                                "height": 100,
                                "duration": 1,
                            },
                        },
                    ],
                }
            )
        ]

    monkeypatch.setattr(MilkyBot, "get_forwarded_messages", fake_get_forwarded_messages)

    forwarded = await get_forwarded_messages(bot, event)
    images = await get_event_media_segments(bot, event, Image)
    videos = await get_event_media_segments(bot, event, Video)

    assert len(forwarded) == 1
    assert [image.url for image in images] == ["https://example.com/image.jpg"]
    assert [video.url for video in videos] == ["https://example.com/video.mp4"]


@pytest.mark.usefixtures("_nonebot_bootstrap")
@pytest.mark.parametrize(
    ("payload", "segment_type", "expected_id"),
    (
        (
            {
                "photo": [
                    {
                        "file_id": "photo-file",
                        "file_unique_id": "photo-unique",
                        "width": 100,
                        "height": 100,
                    }
                ]
            },
            Image,
            "photo-file",
        ),
        (
            {
                "video": {
                    "file_id": "video-file",
                    "file_unique_id": "video-unique",
                    "width": 100,
                    "height": 100,
                    "duration": 1,
                }
            },
            Video,
            "video-file",
        ),
    ),
)
async def test_telegram_forwarded_media_uses_visible_message(
    payload,
    segment_type,
    expected_id,
):
    from hoshino.platform import get_forwarded_messages
    from hoshino.util.media import get_event_media_segments

    bot = TelegramBot(
        TelegramAdapter(get_driver()),
        self_id="10000",
        config=TelegramBotConfig(token="10000:test"),
    )
    event = TelegramMessageEvent.parse_event(
        {
            "message_id": 7,
            "date": 1,
            "chat": {"id": -100123456, "type": "supergroup", "title": "test"},
            "from": {"id": 42, "is_bot": False, "first_name": "Alice"},
            "forward_from": {"id": 43, "is_bot": False, "first_name": "Bob"},
            **payload,
        }
    )

    forwarded = await get_forwarded_messages(bot, event)
    media = await get_event_media_segments(bot, event, segment_type)

    assert len(forwarded) == 1
    assert [segment.id for segment in media] == [expected_id]
