"""Asynchronous media persistence for X posts."""

from __future__ import annotations

import asyncio
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
        posts = [post]
        if isinstance(post.repost, XPost):
            posts.append(post.repost)
        remaining = max(0, max_media)
        merged_images: list[str] = []
        merged_videos: list[str] = []
        for current in posts:
            image_urls = current.images[:remaining]
            remaining -= len(image_urls)
            video_urls = current.videos[:remaining]
            remaining -= len(video_urls)
            current.images = await self._persist_urls(
                current, image_urls, is_video=False, keep_remote=True
            )
            current.videos = await self._persist_urls(
                current, video_urls, is_video=True, keep_remote=False
            )
            merged_images.extend(
                path for path in current.images if path not in merged_images
            )
            merged_videos.extend(
                path for path in current.videos if path not in merged_videos
            )
            if remaining <= 0:
                break
        post.images = merged_images
        post.videos = merged_videos
        return post

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


def _httpx_proxy(proxy: str | None) -> str | None:
    if proxy and proxy.startswith("socks://"):
        return f"socks5://{proxy.removeprefix('socks://')}"
    return proxy


__all__ = ["XMediaStore"]
