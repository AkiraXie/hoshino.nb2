"""X post model built on the shared content contracts."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from typing_extensions import override
from twscrape.models import Media, Tweet

from hoshino.command import UniMessage
from hoshino.content import Post, PostMessage
from hoshino.types import MessageLike


@dataclass
class XPost(Post):
    likes: int = 0
    retweets: int = 0
    replies: int = 0

    @classmethod
    def from_tweet(cls, tweet: Tweet) -> "XPost":
        author = tweet.user.username.lstrip("@")
        date = tweet.date
        if date.tzinfo is None:
            date = date.replace(tzinfo=timezone.utc)
        images, videos = _media_urls(tweet.media)
        source = tweet.retweetedTweet or tweet.quotedTweet
        return cls(
            uid=author,
            id=str(tweet.id),
            content=tweet.rawContent,
            images=images,
            videos=videos,
            timestamp=date.timestamp(),
            url=f"https://fxtwitter.com/{author}/status/{tweet.id}",
            nickname=tweet.user.displayname or author,
            repost=cls.from_tweet(source) if source is not None else None,
            likes=tweet.likeCount,
            retweets=tweet.retweetCount,
            replies=tweet.replyCount,
        )

    @override
    async def get_message(self, **kwargs: Any) -> PostMessage:
        del kwargs
        return PostMessage(
            text=self.format_text(),
            content=self.content,
            images=[_media_resource(value) for value in self.images],
            videos=[_media_resource(value) for value in self.videos],
        )

    @override
    def render_message(self, post_message: PostMessage) -> list[MessageLike]:
        message = UniMessage.text(post_message.text)
        for image in post_message.images:
            message += (
                UniMessage.image(path=image)
                if isinstance(image, Path)
                else UniMessage.image(url=image)
            )
        for video in post_message.videos:
            message += (
                UniMessage.video(path=video)
                if isinstance(video, Path)
                else UniMessage.video(url=video)
            )
        return [message]

    @override
    def get_referer(self) -> str:
        return "https://x.com/"

    def format_text(self) -> str:
        parts = [f"{self.nickname} (@{self.uid})", self.content]
        if self.repost is not None:
            parts.extend(
                [
                    "------------",
                    f"转发/引用 @{self.repost.uid}",
                    self.repost.content,
                ]
            )
        parts.extend(
            [
                f"时间: {datetime.fromtimestamp(self.timestamp).strftime('%Y-%m-%d %H:%M:%S')}",
                f"喜欢: {self.likes}  转发: {self.retweets}  回复: {self.replies}",
                self.url,
            ]
        )
        return "\n".join(part for part in parts if part)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "XPost":
        data = dict(raw)
        repost = data.get("repost")
        data["repost"] = cls.from_dict(repost) if isinstance(repost, dict) else None
        return cls(**data)


def _media_urls(media: Media) -> tuple[list[str], list[str]]:
    images = [photo.url for photo in media.photos]
    videos: list[str] = []
    for video in media.videos:
        if variant := max(video.variants, key=lambda item: item.bitrate, default=None):
            videos.append(variant.url)
    videos.extend(animation.videoUrl for animation in media.animated)
    return images, videos


def _media_resource(value: str) -> str | Path:
    return value if urlparse(value).scheme in {"http", "https"} else Path(value)


__all__ = ["XPost"]
