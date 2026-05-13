import asyncio
import json
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Iterable

from hoshino import Bot, Message, MessageSegment, config
from hoshino.modules.information.utils import PostMessage
from hoshino.util import (
    save_img_by_path,
    save_video_by_path,
    send_group_segments,
)

from ..pw import (
    get_mapp_weibo_screenshot,
    get_weibo_screenshot_desktop,
)
from ..sv import sv

if TYPE_CHECKING:
    from ..post import WeiboPost


weibo_img_dir = config.data_dir / "weiboimages"
weibo_img_dir.mkdir(parents=True, exist_ok=True)
weibo_video_dir = config.data_dir / "weibovideos"
weibo_video_dir.mkdir(parents=True, exist_ok=True)
weibo_msg_dir = config.data_dir / "weibomsgs"
weibo_msg_dir.mkdir(parents=True, exist_ok=True)

WEIBO_MSG_CACHE_TTL = 3 * 60 * 60
CACHE_FILE_CLEANUP_DELAY = 3 * 60 * 60


# =============================================================================
# Internal private classes
# =============================================================================


class _TimedHandleRegistry:
    def __init__(self) -> None:
        self._handles: dict[str, asyncio.Handle] = {}

    def replace(
        self,
        key: str,
        delay: float,
        callback,
        *args,
    ) -> None:
        handle = self._handles.pop(key, None)
        if handle and not handle.cancelled():
            handle.cancel()
        loop = asyncio.get_running_loop()
        self._handles[key] = loop.call_later(delay, callback, *args)

    def pop(self, key: str) -> asyncio.Handle | None:
        return self._handles.pop(key, None)


class _MessageIdCache:
    def __init__(self, ttl: float) -> None:
        self._ttl = ttl
        self._values: dict[str, str] = {}
        self._registry = _TimedHandleRegistry()

    def remember(self, msg_id: int | str, uid: str, post_id: str) -> None:
        key = str(msg_id)
        self._values[key] = f"{uid}_{post_id}"
        self._registry.replace(key, self._ttl, self._expire, key)

    def get(self, msg_id: int | str) -> str:
        return self._values.get(str(msg_id), "")

    def _expire(self, key: str) -> None:
        self._values.pop(key, None)
        handle = self._registry.pop(key)
        if handle and not handle.cancelled():
            handle.cancel()


class _TempFileCleaner:
    def __init__(self, delay: float) -> None:
        self._delay = delay
        self._registry = _TimedHandleRegistry()

    def schedule(self, paths: list[Path]) -> None:
        for path in paths:
            self._registry.replace(str(path), self._delay, self._delete, str(path))

    def _delete(self, filepath_str: str) -> None:
        self._registry.pop(filepath_str)
        try:
            path = Path(filepath_str)
            if path.exists():
                path.unlink()
                sv.logger.debug(f"已清理缓存文件: {filepath_str}")
        except Exception as e:
            sv.logger.error(f"清理缓存文件失败: {filepath_str} error={e}")


class _PostAssetService:
    def iter_posts(self, post: "WeiboPost") -> Iterable["WeiboPost"]:
        current = post
        while current:
            yield current
            current = current.repost

    async def build_message(
        self,
        post: "WeiboPost",
        *,
        full: bool,
        with_screenshot: bool,
        screenshot_timeout: float,
    ) -> PostMessage:
        image_paths = await self.download_images(post)
        content = "\n".join(post._build_content_lines())
        header = post._build_text_header()

        if not full:
            _file_cleaner.schedule(image_paths)
            return PostMessage(text=header, images=image_paths, content=content)

        video_paths = await self.download_videos(post)
        screenshot = None
        if with_screenshot:
            screenshot = await self.take_screenshot(post, timeout=screenshot_timeout)
        _file_cleaner.schedule(image_paths + video_paths)
        return PostMessage(
            text=header,
            content=content,
            screenshot=screenshot,
            images=image_paths,
            videos=video_paths,
        )

    async def download_images(self, post: "WeiboPost") -> list[Path]:
        return await self._download_recursive(
            post,
            base_dir=weibo_img_dir,
            suffix=".jpg",
            urls_getter=lambda item: item.images,
            saver=save_img_by_path,
        )

    async def download_videos(self, post: "WeiboPost") -> list[Path]:
        return await self._download_recursive(
            post,
            base_dir=weibo_video_dir,
            suffix=".mp4",
            urls_getter=lambda item: item.videos,
            saver=save_video_by_path,
        )

    async def _download_recursive(
        self,
        post: "WeiboPost",
        *,
        base_dir: Path,
        suffix: str,
        urls_getter,
        saver,
    ) -> list[Path]:
        results: list[Path] = []
        for item in self.iter_posts(post):
            results.extend(
                await self._download_for_post(
                    item,
                    base_dir=base_dir,
                    suffix=suffix,
                    urls=urls_getter(item),
                    saver=saver,
                )
            )
        return results

    async def _download_for_post(
        self,
        post: "WeiboPost",
        *,
        base_dir: Path,
        suffix: str,
        urls: list[str],
        saver,
    ) -> list[Path]:
        headers = {"referer": post.get_referer()}
        dirpath = post._get_download_dir(base_dir)

        async def _download_one(index: int, url: str) -> Path | None:
            filepath = dirpath / post._build_download_filename(index, suffix)
            if filepath.exists():
                return filepath
            try:
                saved = await saver(url, filepath, True, headers=headers)
            except Exception as e:
                sv.logger.error(f"Error downloading resource {url}: {e}")
                return None
            if saved:
                return saved
            sv.logger.error(f"Failed to save resource {url}")
            return None

        tasks = [_download_one(index, url) for index, url in enumerate(urls)]
        resolved = await asyncio.gather(*tasks, return_exceptions=True)
        saved_paths: list[Path] = []
        for item in resolved:
            if isinstance(item, Path):
                saved_paths.append(item)
            elif isinstance(item, Exception):
                sv.logger.error(
                    f"Error in download task: {item}, urls={urls}, id={post.id}"
                )
        return saved_paths

    async def take_screenshot(
        self,
        post: "WeiboPost",
        *,
        timeout: float,
    ) -> Path | bytes | None:
        screenshot_task = None
        if post.description == "mapp":
            screenshot_task = get_mapp_weibo_screenshot(post.url, timeout=timeout)
        else:
            screenshot_task = get_weibo_screenshot_desktop(post.url, timeout=timeout)

        if not screenshot_task:
            return None
        try:
            return await screenshot_task
        except Exception as e:
            sv.logger.error(f"Error fetching screenshot: {e}")
            return None


class _PostArchiveStore:
    async def save(self, post: "WeiboPost", post_message: PostMessage) -> PostMessage:
        uid_dir = post._get_download_dir(weibo_msg_dir)
        save_dir = uid_dir / post.id
        save_dir.mkdir(parents=True, exist_ok=True)

        await self._save_avatar(post, uid_dir)
        self._write_metadata(post, post_message, save_dir)

        if post_message.screenshot:
            await self._save_resource(
                post_message.screenshot,
                save_dir / "screenshot.jpg",
                referer=post.get_referer(),
            )

        await self._save_indexed_resources(
            post_message.images,
            save_dir / "images",
            suffix=".jpg",
            referer=post.get_referer(),
        )
        await self._save_indexed_resources(
            post_message.videos,
            save_dir / "videos",
            suffix=".mp4",
            referer=post.get_referer(),
        )

        return PostMessage(
            text=post_message.text,
            content=post_message.content,
            screenshot=(save_dir / "screenshot.jpg") if post_message.screenshot else None,
            images=[save_dir / "images" / f"{i + 1}.jpg" for i in range(len(post_message.images))],
            videos=[save_dir / "videos" / f"{i + 1}.mp4" for i in range(len(post_message.videos))],
        )

    async def load(self, uid: str, post_id: str) -> PostMessage | None:
        msg_dir = weibo_msg_dir / uid / post_id
        if not msg_dir.exists():
            return await self._refetch(uid, post_id)

        metadata = self._read_metadata(msg_dir, uid, post_id)
        text = str(metadata.get("text", "") or "")
        content = str(metadata.get("content", "") or "")
        detail_url = f"https://weibo.com/{uid}/{post_id}"
        if detail_url not in text:
            text = "\n".join(part for part in (text, f"微博详情: {detail_url}") if part)
        if content and content in text:
            content = ""

        return PostMessage(
            text=text,
            content=content,
            screenshot=self._existing_file(msg_dir / "screenshot.jpg"),
            images=self._sorted_files(msg_dir / "images", "*.jpg"),
            videos=self._sorted_files(msg_dir / "videos", "*.mp4"),
        )

    async def _refetch(self, uid: str, post_id: str) -> PostMessage | None:
        sv.logger.warning(
            f"weibo post not found in cache, refetching: uid={uid} post_id={post_id}"
        )
        from ..request import parse_weibo_with_id

        post = await parse_weibo_with_id(post_id)
        if not post:
            return None
        return await post.get_message()

    async def _save_avatar(self, post: "WeiboPost", uid_dir: Path) -> None:
        if not post.user_avatar_image:
            return
        avatar_path = uid_dir / "user_avatar.jpg"
        is_stale = avatar_path.exists() and (
            datetime.fromtimestamp(avatar_path.stat().st_mtime).date()
            != datetime.now().date()
        )
        if avatar_path.exists() and not is_stale:
            return
        try:
            await self._save_resource(
                post.user_avatar_image,
                avatar_path,
                referer=post.get_referer(),
            )
        except Exception as e:
            sv.logger.warning(f"Failed to save avatar for {post.uid}: {e}")

    def _write_metadata(
        self,
        post: "WeiboPost",
        post_message: PostMessage,
        save_dir: Path,
    ) -> None:
        metadata = {
            "uid": post.uid,
            "id": post.id,
            "text": post_message.text,
            "content": post_message.content,
            "url": post.url,
            "nickname": post.nickname,
            "timestamp": post.timestamp,
        }
        (save_dir / "message.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    async def _save_indexed_resources(
        self,
        resources: list[bytes | str | Path],
        target_dir: Path,
        *,
        suffix: str,
        referer: str,
    ) -> None:
        for index, resource in enumerate(resources, start=1):
            await self._save_resource(
                resource,
                target_dir / f"{index}{suffix}",
                referer=referer,
            )

    async def _save_resource(
        self,
        resource: bytes | str | Path,
        target: Path,
        *,
        referer: str,
    ) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(resource, bytes):
            target.write_bytes(resource)
            return

        source_path = Path(resource)
        if source_path.exists():
            if source_path.resolve() != target.resolve():
                shutil.copy2(source_path, target)
            return

        if target.suffix == ".mp4":
            saved = await save_video_by_path(
                resource,
                target,
                True,
                headers={"referer": referer},
            )
        else:
            saved = await save_img_by_path(
                resource,
                target,
                True,
                headers={"referer": referer},
            )
        if not saved:
            raise FileNotFoundError(f"failed to save resource: {resource}")

    def _read_metadata(self, msg_dir: Path, uid: str, post_id: str) -> dict:
        metadata_path = msg_dir / "message.json"
        if not metadata_path.exists():
            return {}
        try:
            loaded = json.loads(metadata_path.read_text(encoding="utf-8"))
            return loaded if isinstance(loaded, dict) else {}
        except (OSError, json.JSONDecodeError) as e:
            sv.logger.warning(
                f"failed to load cached weibo metadata: uid={uid} post_id={post_id} error={e}"
            )
            return {}

    def _existing_file(self, path: Path) -> Path | None:
        return path if path.exists() else None

    def _sorted_files(self, directory: Path, pattern: str) -> list[Path]:
        if not directory.exists():
            return []
        return sorted(directory.glob(pattern), key=lambda item: item.name)


class _MessageRenderer:
    def build_image_messages(self, image_paths: list[Path]) -> list[Message | MessageSegment]:
        if not image_paths:
            return []
        segments = [MessageSegment.image(image_path) for image_path in image_paths]
        messages: list[Message | MessageSegment] = []
        chunk_size = 4
        for divisor in (7, 6, 5, 4, 3):
            if len(segments) % divisor == 0:
                chunk_size = divisor
                break
        for index in range(0, len(segments), chunk_size):
            messages.append(Message(segments[index : index + chunk_size]))
        return messages

    def render(
        self,
        post_message: PostMessage,
        post: "WeiboPost | None" = None,
    ) -> list[Message | MessageSegment]:
        head = post_message.text or ""
        if post_message.screenshot:
            head += "\n" + str(MessageSegment.image(post_message.screenshot))
        elif post_message.content:
            head += "\n" + post_message.content
        if post:
            tail = post._build_text_tail()
            if tail:
                head += "\n" + tail

        messages: list[Message | MessageSegment] = []
        if head:
            messages.append(Message(head))
        messages.extend(self.build_image_messages(post_message.images))
        messages.extend(MessageSegment.video(video) for video in post_message.videos)
        return messages

class _MessageDispatcher:
    async def send_messages(
        self,
        bot: Bot,
        gid: int,
        msgs: list[Message | MessageSegment] | None = None,
        *,
        uid: str = "",
        post_id: str = "",
    ) -> dict:
        if not msgs:
            return {}
        sv.logger.info(
            "微博发送普通消息: "
            f"group={gid} uid={uid} post={post_id} msg_count={len(msgs)}"
        )
        result = await bot.send_group_msg(group_id=gid, message=msgs[0])
        for message in msgs[1:]:
            await bot.send_group_msg(group_id=gid, message=message)
            await asyncio.sleep(0.3)
        return result

    async def send_segments(
        self,
        bot: Bot,
        gid: int,
        msgs: list[Message | MessageSegment] | None = None,
        *,
        uid: str = "",
        post_id: str = "",
    ) -> dict:
        if not msgs:
            return {}
        sv.logger.info(
            "微博发送分段消息: "
            f"group={gid} uid={uid} post={post_id} msg_count={len(msgs)}"
        )
        result = await bot.send_group_msg(group_id=gid, message=msgs[0])
        if len(msgs) > 1:
            await asyncio.sleep(0.3)
            await send_group_segments(bot, gid, msgs[1:])
        return result


# =============================================================================
# Module-level instances
# =============================================================================

_message_id_cache = _MessageIdCache(WEIBO_MSG_CACHE_TTL)
_file_cleaner = _TempFileCleaner(CACHE_FILE_CLEANUP_DELAY)
_asset_service = _PostAssetService()
_archive_store = _PostArchiveStore()
_renderer = _MessageRenderer()
_dispatcher = _MessageDispatcher()


# =============================================================================
# Public wrapper functions (thin delegations to the instances above)
# =============================================================================


def schedule_file_cleanup(paths: list[Path]) -> None:
    _file_cleaner.schedule(paths)


def cache_weibo_msg_id(msg_id: int | str, uid: str, post_id: str) -> None:
    _message_id_cache.remember(msg_id, uid, post_id)


def get_cached_weibo_uid_id(msg_id: int | str) -> str:
    return _message_id_cache.get(msg_id)


async def download_post_images(post: "WeiboPost") -> list[Path]:
    return await _asset_service.download_images(post)


async def download_post_videos(post: "WeiboPost") -> list[Path]:
    return await _asset_service.download_videos(post)


async def take_post_screenshot(
    post: "WeiboPost",
    timeout: float = 6.0,
) -> Path | bytes | None:
    return await _asset_service.take_screenshot(post, timeout=timeout)


def build_image_messages(
    image_paths: list[Path],
) -> list[Message | MessageSegment]:
    return _renderer.build_image_messages(image_paths)


def render_messages(
    post_message: PostMessage,
    post: "WeiboPost | None" = None,
) -> list[Message | MessageSegment]:
    return _renderer.render(post_message, post=post)


async def send_weibo_messages(
    bot: Bot,
    gid: int,
    msgs: list[Message | MessageSegment] | None = None,
    *,
    uid: str = "",
    post_id: str = "",
) -> dict:
    return await _dispatcher.send_messages(bot, gid, msgs, uid=uid, post_id=post_id)


async def send_weibo_segments(
    bot: Bot,
    gid: int,
    msgs: list[Message | MessageSegment] | None = None,
    *,
    uid: str = "",
    post_id: str = "",
) -> dict:
    return await _dispatcher.send_segments(bot, gid, msgs, uid=uid, post_id=post_id)


async def save_post_message(
    post: "WeiboPost",
    post_message: PostMessage,
) -> PostMessage:
    return await _archive_store.save(post, post_message)


async def post_msg_from_uid_id(
    uid: str,
    post_id: str,
) -> PostMessage | None:
    return await _archive_store.load(uid, post_id)


@dataclass
class WeiboDispatchTask:
    post: "WeiboPost"
    message: PostMessage
    group_id: int

    def get_id(self) -> str:
        return f"{self.group_id}_{self.post.id}"


# =============================================================================
# Internal helper functions
# =============================================================================


async def get_post_message(
    post,
    *,
    with_screenshot: bool = True,
    screenshot_timeout: float = 6.0,
) -> PostMessage:
    image_paths = await _asset_service.download_images(post)
    content = "\n".join(post._build_content_lines())
    header = post._build_text_header()
    video_paths = await _asset_service.download_videos(post)
    screenshot = None
    if with_screenshot:
        screenshot = await _asset_service.take_screenshot(post, timeout=screenshot_timeout)
    _file_cleaner.schedule([*image_paths, *video_paths])
    return PostMessage(
        text=header,
        content=content,
        screenshot=screenshot,
        images=image_paths,
        videos=video_paths,
    )


def filter_image_post(message: PostMessage) -> PostMessage | None:
    if not message.images:
        return None
    return PostMessage(
        text=message.text,
        content=message.content,
        screenshot=message.screenshot,
        images=list(message.images),
        videos=list(message.videos),
    )


def remove_screenshot(message: PostMessage) -> PostMessage:
    return PostMessage(
        text=message.text,
        content=message.content,
        screenshot=None,
        images=list(message.images),
        videos=list(message.videos),
    )


def remove_videos(message: PostMessage) -> PostMessage:
    return PostMessage(
        text=message.text,
        content=message.content,
        screenshot=message.screenshot,
        images=list(message.images),
        videos=[],
    )


def adapt_post_message(
    message: PostMessage,
    group_config,
    *,
    busy: bool,
) -> PostMessage | None:
    filtered = filter_image_post(message) if bool(group_config.only_pic) else message
    if not filtered:
        return None

    adapted = filtered
    if not bool(group_config.send_screenshot) or busy:
        adapted = remove_screenshot(adapted)
    if busy:
        adapted = remove_videos(adapted)
    return adapted


async def send_post_message(
    bot: Bot,
    gid: int,
    post,
    post_message: PostMessage | None = None,
    *,
    messages: list[Message | MessageSegment] | None = None,
    use_segments: bool = False,
) -> dict:
    final_messages = messages
    if final_messages is None:
        if post_message is None:
            return {}
        final_messages = render_messages(post_message, post=post)
    if use_segments:
        return await _dispatcher.send_segments(
            bot=bot,
            gid=gid,
            msgs=final_messages,
            uid=post.uid,
            post_id=post.id,
        )
    return await _dispatcher.send_messages(
        bot=bot,
        gid=gid,
        msgs=final_messages,
        uid=post.uid,
        post_id=post.id,
    )
