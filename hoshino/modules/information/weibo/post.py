from dataclasses import dataclass
from pathlib import Path
import re
from typing import override
from urllib.parse import unquote, urlparse

from bs4 import BeautifulSoup

from hoshino.types import Bot, Message, MessageSegment
from hoshino.modules.information.utils import PostMessage

from ..utils import Post, clean_filename
from .internal.post_runtime import (
    get_post_message,
    render_messages,
    save_post_message,
    send_post_message,
)
from .sv import sv


_IMAGE_URL_PATTERN = re.compile(
    r"\.(?:jpe?g|png|gif|webp|bmp|heic|heif|avif)(?:$|[?#&])",
    re.IGNORECASE,
)
_VIDEO_URL_PATTERN = re.compile(
    r"\.(?:mp4|m4v|mov|webm|m3u8)(?:$|[?#&])",
    re.IGNORECASE,
)


def normalize_media_url(url: str) -> str:
    normalized = unquote(url.strip())
    if normalized.startswith("//"):
        normalized = "https:" + normalized
    sinaurl_prefix = "https://weibo.cn/sinaurl?u="
    if normalized.startswith(sinaurl_prefix):
        normalized = unquote(normalized.removeprefix(sinaurl_prefix))
    return normalized


def classify_media_url(url: str) -> tuple[str, str]:
    normalized = normalize_media_url(url)
    if not normalized:
        return "", ""

    lowered = normalized.lower()
    parsed = urlparse(normalized)
    host = parsed.netloc.lower()

    if _IMAGE_URL_PATTERN.search(lowered) or "sinaimg.cn" in host:
        return normalized, ""
    if _VIDEO_URL_PATTERN.search(lowered) or "weibocdn.com" in host:
        return "", normalized
    return "", ""


def build_content_lines(post) -> list[str]:
    lines = []
    if post.content:
        lines.append(post.content)
    if post.repost:
        lines.append("------------")
        lines.append("转发自 " + post.repost.nickname)
        lines.append(post.repost.content)
        lines.append("------------")
    return lines


def build_text_header(post) -> str:
    return f"{post.nickname} 微博~" if post.nickname else ""


def build_text_tail(post) -> str:
    parts = []
    if post.repost and post.repost.url:
        parts.append(f"源微博详情: {post.repost.url}")
    if post.url:
        parts.append(f"微博详情: {post.url}")
    return "\n".join(parts)


def get_download_dir(post, base_dir: Path) -> Path:
    uid_part = clean_filename(post.uid)
    dirpath = base_dir / uid_part
    dirpath.mkdir(parents=True, exist_ok=True)
    return dirpath


def build_download_filename(post, index: int, suffix: str) -> str:
    content_source = post.content or post.title or post.id
    content_part = clean_filename(content_source[:20])
    id_part = clean_filename(post.id)
    return f"{content_part}_{id_part}_{index}{suffix}"


def has_any_images(post) -> bool:
    if post.images:
        return True
    return bool(post.repost and has_any_images(post.repost))


@dataclass
class WeiboPost(Post):
    """微博POST数据类"""

    user_avatar_image: str = ""

    @override
    def get_referer(self) -> str:
        return "https://weibo.com"

    def _get_download_dir(self, base_dir: Path) -> Path:
        return get_download_dir(self, base_dir)

    def _build_download_filename(self, i: int, suffix: str) -> str:
        return build_download_filename(self, i, suffix)

    def _has_any_images(self) -> bool:
        return has_any_images(self)

    def _append_image(self, image_url: str) -> None:
        if image_url and image_url not in self.images:
            self.images.append(image_url)

    def _append_video(self, video_url: str) -> None:
        if video_url and video_url not in self.videos:
            self.videos.append(video_url)

    def _get_text(self, raw_text: str) -> str:
        text = raw_text.replace("<br/>", "\n").replace("<br />", "\n")
        soup = BeautifulSoup(text, "lxml")

        if not soup:
            self.content = text
            return text

        for br in soup.find_all("br"):
            br.replace_with("\n")

        for a in soup.find_all("a", href=True):
            href = normalize_media_url(a["href"])
            image_url, video_url = classify_media_url(href)

            if image_url or video_url:
                self._append_image(image_url)
                self._append_video(video_url)
                a.decompose()
                continue

            span = a.find("span", class_="surl-text")
            if not span:
                continue

            link_text = span.get_text()
            if (
                not link_text.startswith("#")
                and not link_text.endswith("#")
                and a["href"].startswith("https://weibo.cn/sinaurl?u=")
            ):
                span.string = f"{link_text}( {href} )"

        parsed_text = soup.get_text()
        self.content = parsed_text
        return parsed_text

    def _build_content_lines(self) -> list[str]:
        return build_content_lines(self)

    def _build_text_header(self) -> str:
        return build_text_header(self)

    def _build_text_tail(self) -> str:
        return build_text_tail(self)

    @override
    async def get_message(
        self,
        with_screenshot: bool = True,
        screenshot_timeout: float = 6.0,
        **kwargs,
    ) -> PostMessage:
        return await get_post_message(
            self,
            with_screenshot=with_screenshot,
            screenshot_timeout=screenshot_timeout,
        )

    @override
    def render_message(
        self, post_message: PostMessage
    ) -> list[Message | MessageSegment]:
        return render_messages(post_message, post=self)

    async def send(
        self,
        bot: Bot,
        gid: int,
        post_message: PostMessage,
        *,
        use_segments: bool = False,
    ) -> dict:
        return await send_post_message(
            bot,
            gid,
            self,
            post_message,
            use_segments=use_segments,
        )

    async def save(self, post_message: PostMessage) -> PostMessage:
        return await save_post_message(self, post_message)
