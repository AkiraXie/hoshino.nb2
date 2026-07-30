"""Asynchronous media persistence for X posts."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from urllib.parse import urlparse

import httpx

from hoshino.core.config import config

from .post import XPost
from .sv import sv


MAX_VIDEO_BYTES = 45 * 1024 * 1024


class XMediaStore:
    def __init__(self) -> None:
        settings = sv.get_config()
        self.root = config.data_dir / "x"
        self.errors: list[tuple[str, Exception]] = []
        self.client = httpx.AsyncClient(
            proxy=_httpx_proxy(settings.proxy),
            timeout=settings.request_timeout_seconds,
            follow_redirects=True,
            trust_env=False,
            headers={"Referer": "https://x.com/", "User-Agent": "Mozilla/5.0"},
        )

    async def close(self) -> None:
        await self.client.aclose()

    def pop_errors(self) -> list[tuple[str, Exception]]:
        errors, self.errors = self.errors, []
        return errors

    async def persist(self, post: XPost, max_media: int) -> XPost:
        # The original tweet owns its media, so process the repost first: shared
        # media lands in the original's directory (root/<orig_uid>/<orig_id>/).
        # Together with the exists-check in _download, every later retweet of the
        # same original reuses that single file instead of saving another copy.
        chain: list[XPost] = []
        if isinstance(post.repost, XPost):
            chain.append(post.repost)
        chain.append(post)
        remaining = max(0, max_media)
        merged_images: list[str] = []
        merged_videos: list[str] = []
        # A retweet/quote re-carries the source tweet's media, so the same URL
        # appears on both the post and its repost. Deduplicate by the source URL
        # up front; the per-post download paths differ (they embed the post id),
        # so comparing downloaded paths would miss these dupes.
        seen_urls: set[str] = set()
        for current in chain:
            image_urls = _take_unseen(current.images, seen_urls, remaining)
            remaining -= len(image_urls)
            video_urls = _take_unseen(current.videos, seen_urls, remaining)
            remaining -= len(video_urls)
            current.images = await self._persist_urls(
                current, image_urls, is_video=False, keep_remote=True
            )
            current.videos = await self._persist_urls(
                current, video_urls, is_video=True, keep_remote=False
            )
            merged_images.extend(current.images)
            merged_videos.extend(current.videos)
            if remaining <= 0:
                break
        post.images = merged_images
        post.videos = merged_videos
        return post

    async def write_metadata(self, post: XPost) -> None:
        """Write message.json alongside persisted media for structured archive."""
        post_dir = self.root / post.uid / post.id
        metadata_path = post_dir / "message.json"
        if metadata_path.exists():
            return

        repost_data = None
        if isinstance(post.repost, XPost):
            repost_data = {
                "uid": post.repost.uid,
                "id": post.repost.id,
                "content": post.repost.content,
                "nickname": post.repost.nickname,
                "url": post.repost.url,
            }

        # Store relative filenames for images/videos
        image_names = [Path(p).name for p in post.images if not p.startswith("http")]
        video_names = [Path(p).name for p in post.videos if not p.startswith("http")]

        metadata = {
            "uid": post.uid,
            "id": post.id,
            "content": post.content,
            "nickname": post.nickname,
            "timestamp": post.timestamp,
            "url": post.url,
            "likes": post.likes,
            "images": image_names,
            "videos": video_names,
            "repost": repost_data,
        }

        await asyncio.to_thread(post_dir.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(
            metadata_path.write_text,
            json.dumps(metadata, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    async def _persist_urls(
        self,
        post: XPost,
        urls: list[str],
        *,
        is_video: bool,
        keep_remote: bool,
    ) -> list[str]:
        paths = await asyncio.gather(
            *(self._download(post, url, is_video) for url in urls)
        )
        return [
            str(path) if path is not None else url
            for url, path in zip(urls, paths, strict=True)
            if path is not None or keep_remote
        ]

    async def _download(self, post: XPost, url: str, is_video: bool) -> Path | None:
        filename = Path(urlparse(url).path).name or f"media-{abs(hash(url))}"
        target = self.root / post.uid / post.id / filename
        if target.exists():
            return target
        await asyncio.to_thread(target.parent.mkdir, parents=True, exist_ok=True)
        temporary = target.with_name(f".{target.name}.part")
        try:
            async with self.client.stream("GET", url) as response:
                response.raise_for_status()
                size = int(response.headers.get("content-length", 0) or 0)
                if is_video and size > MAX_VIDEO_BYTES:
                    return None
                handle = await asyncio.to_thread(temporary.open, "wb")
                try:
                    total = 0
                    async for chunk in response.aiter_bytes():
                        total += len(chunk)
                        if is_video and total > MAX_VIDEO_BYTES:
                            raise ValueError("X video exceeds the upload size limit")
                        await asyncio.to_thread(handle.write, chunk)
                finally:
                    await asyncio.to_thread(handle.close)
            await asyncio.to_thread(temporary.replace, target)
            return target
        except (httpx.HTTPError, OSError, ValueError) as exc:
            await asyncio.to_thread(temporary.unlink, missing_ok=True)
            sv.logger.warning(
                f"X media download failed: post={post.id} type="
                f"{'video' if is_video else 'image'} error={type(exc).__name__}"
            )
            self.errors.append((post.uid, exc))
            return None


def _take_unseen(urls: list[str], seen: set[str], limit: int) -> list[str]:
    taken: list[str] = []
    for url in urls:
        if len(taken) >= limit or url in seen:
            continue
        seen.add(url)
        taken.append(url)
    return taken


def _httpx_proxy(proxy: str | None) -> str | None:
    if proxy and proxy.startswith("socks://"):
        return f"socks5://{proxy.removeprefix('socks://')}"
    return proxy


__all__ = ["XMediaStore"]
