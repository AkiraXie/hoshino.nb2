from dataclasses import dataclass
from datetime import datetime
import asyncio
import functools
import json
import nonebot
from pathlib import Path
import re
import shutil
from typing import override
from urllib.parse import unquote, urlparse
from bs4 import BeautifulSoup
from time import time
from hoshino import Bot, Message, Service, MessageSegment, config
from hoshino.util import (
    aiohttpx,
    get_cookies,
    get_redirect,
    save_video_by_path,
    save_img_by_path,
    sucmd,
    send_group_segments,
    send_to_superuser,
)
from .pw import (
    get_mapp_weibo_screenshot,
    get_weibo_cookies_from_local,
    get_weibo_screenshot_mobile,
    get_weibo_screenshot_desktop,
)
from hoshino import on_startup

from ..utils import Post, PostMessage, clean_filename
from hoshino.util import save_cookies
from .db import WeiboConfig, get_group_config, remove_subscriptions_by_uid

sv = Service("weibo", enable_on_default=False, visible=False)

weibo_img_dir = config.data_dir / "weiboimages"
weibo_img_dir.mkdir(parents=True, exist_ok=True)
weibo_video_dir = config.data_dir / "weibovideos"
weibo_video_dir.mkdir(parents=True, exist_ok=True)
weibo_msg_dir = config.data_dir / "weibomsgs"
weibo_msg_dir.mkdir(parents=True, exist_ok=True)

WEIBO_MSG_CACHE_TTL = 3 * 60 * 60
weibo_msg_cache: dict[str, str] = {}
_weibo_msg_cache_handles: dict[str, asyncio.Handle] = {}

CACHE_FILE_CLEANUP_DELAY = 3 * 60 * 60
_file_cleanup_handles: dict[str, asyncio.Handle] = {}

_IMAGE_URL_PATTERN = re.compile(
    r"\.(?:jpe?g|png|gif|webp|bmp|heic|heif|avif)(?:$|[?#&])",
    re.IGNORECASE,
)
_VIDEO_URL_PATTERN = re.compile(
    r"\.(?:mp4|m4v|mov|webm|m3u8)(?:$|[?#&])",
    re.IGNORECASE,
)


def _normalize_media_url(url: str) -> str:
    normalized = unquote(url.strip())
    if normalized.startswith("//"):
        normalized = "https:" + normalized
    sinaurl_prefix = "https://weibo.cn/sinaurl?u="
    if normalized.startswith(sinaurl_prefix):
        normalized = unquote(normalized.removeprefix(sinaurl_prefix))
    return normalized


def _classify_media_url(url: str) -> tuple[str, str]:
    normalized = _normalize_media_url(url)
    if not normalized:
        return "", ""

    lowered = normalized.lower()
    parsed = urlparse(normalized)
    host = parsed.netloc.lower()

    if _IMAGE_URL_PATTERN.search(lowered) or "sinaimg.cn" in host:
        return normalized, ""
    if (
        _VIDEO_URL_PATTERN.search(lowered)
        or "video.weibo.com" in host
        or "weibocdn.com" in host
    ):
        return "", normalized
    return "", ""


def _delete_weibo_msg_cache(msg_id: str) -> None:
    weibo_msg_cache.pop(msg_id, None)
    handle = _weibo_msg_cache_handles.pop(msg_id, None)
    if handle and not handle.cancelled():
        handle.cancel()


def _delete_cached_file(filepath_str: str) -> None:
    _file_cleanup_handles.pop(filepath_str, None)
    try:
        p = Path(filepath_str)
        if p.exists():
            p.unlink()
            sv.logger.debug(f"已清理缓存文件: {filepath_str}")
    except Exception as e:
        sv.logger.error(f"清理缓存文件失败: {filepath_str} error={e}")


def schedule_file_cleanup(paths: list[Path]) -> None:
    loop = asyncio.get_running_loop()
    for p in paths:
        key = str(p)
        old_handle = _file_cleanup_handles.pop(key, None)
        if old_handle and not old_handle.cancelled():
            old_handle.cancel()
        _file_cleanup_handles[key] = loop.call_later(
            CACHE_FILE_CLEANUP_DELAY,
            _delete_cached_file,
            key,
        )


def cache_weibo_msg_id(msg_id: int | str, uid: str, post_id: str) -> None:
    msg_id_key = str(msg_id)
    old_handle = _weibo_msg_cache_handles.pop(msg_id_key, None)
    if old_handle and not old_handle.cancelled():
        old_handle.cancel()

    weibo_msg_cache[msg_id_key] = f"{uid}_{post_id}"
    loop = asyncio.get_running_loop()
    _weibo_msg_cache_handles[msg_id_key] = loop.call_later(
        WEIBO_MSG_CACHE_TTL,
        _delete_weibo_msg_cache,
        msg_id_key,
    )


def get_cached_weibo_uid_id(msg_id: int | str) -> str:
    return weibo_msg_cache.get(str(msg_id), "")


def render_post_message(post_message: PostMessage) -> list[Message | MessageSegment]:
    messages: list[Message | MessageSegment] = []
    text = ""
    if post_message.text:
        text += post_message.text
    if post_message.screenshot:
        text += "\n" + str(MessageSegment.image(post_message.screenshot))
    elif post_message.content:
        text += "\n" + post_message.content
    messages.append(Message(text))

    image_segments = [
        MessageSegment.image(image_path) for image_path in post_message.images
    ]
    if image_segments:
        chunk_size = 4
        for divisor in (7, 6, 5, 4, 3):
            if len(image_segments) % divisor == 0:
                chunk_size = divisor
                break
        for index in range(0, len(image_segments), chunk_size):
            messages.append(Message(image_segments[index : index + chunk_size]))

    messages.extend(
        MessageSegment.video(video_path) for video_path in post_message.videos
    )
    return messages


@dataclass
class WeiboPost(Post):
    """微博POST数据类"""

    user_avatar_image: str = ""

    @override
    def get_referer(self) -> str:
        """获取微博的referer"""
        return "https://weibo.com"

    def _get_download_dir(self, base_dir: Path) -> Path:
        uid_part = clean_filename(self.uid)
        dirpath = base_dir / uid_part
        dirpath.mkdir(parents=True, exist_ok=True)
        return dirpath

    def _build_download_filename(self, i: int, suffix: str) -> str:
        content_source = self.content or self.title or self.id
        content_part = clean_filename(content_source[:20])
        id_part = clean_filename(self.id)
        return f"{content_part}_{id_part}_{i}{suffix}"

    def _has_any_images(self) -> bool:
        if self.images:
            return True
        return bool(self.repost and self.repost._has_any_images())

    def _append_image(self, image_url: str) -> None:
        if image_url and image_url not in self.images:
            self.images.append(image_url)

    def _append_video(self, video_url: str) -> None:
        if video_url and video_url not in self.videos:
            self.videos.append(video_url)

    def _append_media_from_url(self, url: str) -> None:
        image_url, video_url = _classify_media_url(url)
        self._append_image(image_url)
        self._append_video(video_url)

    def _get_text(self, raw_text: str) -> str:
        text = raw_text.replace("<br/>", "\n").replace("<br />", "\n")
        soup = BeautifulSoup(text, "lxml")

        if not soup:
            self.content = text
            return text

        for br in soup.find_all("br"):
            br.replace_with("\n")

        for a in soup.find_all("a", href=True):
            href = _normalize_media_url(a["href"])
            image_url, video_url = _classify_media_url(href)

            # 媒体链接：提取资源并移除标签（避免 "查看图片" 等残留文本）
            if image_url or video_url:
                self._append_image(image_url)
                self._append_video(video_url)
                a.decompose()
                continue

            # 非媒体链接：展开 surl-text 中的短链
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

        # for img in soup.find_all("img"):
        #     if img.find_parent("a", href=True):
        #         continue
        #     for attr in ("src", "data-src", "bak_src"):
        #         img_url = img.get(attr)
        #         if img_url:
        #             self._append_media_from_url(img_url)
        #             break

        # for media_tag in soup.find_all(["video", "source"]):
        #     media_url = media_tag.get("src")
        #     if media_url:
        #         self._append_media_from_url(media_url)

        parsed_text = soup.get_text()
        self.content = parsed_text
        return parsed_text

    async def _send_rendered_segments(
        self,
        msgs: list[Message | MessageSegment],
        bot: Bot,
        gid: int,
    ) -> dict:
        if not msgs:
            return {}
        head = msgs[0]
        res = await bot.send_group_msg(group_id=gid, message=head)
        if len(msgs) > 1:
            await asyncio.sleep(0.3)
            await send_group_segments(bot, gid, msgs[1:])
        return res

    async def send_message(
        self,
        bot: Bot | None = None,
        gid: int | None = None,
        msgs: list[Message | MessageSegment] | None = None,
    ) -> dict:
        if not msgs:
            return {}
        sv.logger.info(
            "微博发送普通消息: "
            f"group={gid} uid={self.uid} post={self.id} msg_count={len(msgs)}"
        )
        head = msgs[0]
        res = await bot.send_group_msg(group_id=gid, message=head)
        for message in msgs[1:]:
            await bot.send_group_msg(group_id=gid, message=message)
            await asyncio.sleep(0.3)
        return res

    async def send_segments(
        self,
        bot: Bot | None = None,
        gid: int | None = None,
        msgs: list[Message | MessageSegment] | None = None,
    ) -> dict:
        if not msgs:
            return {}
        sv.logger.info(
            "微博发送分段消息: "
            f"group={gid} uid={self.uid} post={self.id} msg_count={len(msgs)}"
        )
        return await self._send_rendered_segments(msgs, bot, gid)

    async def download_images(self) -> list[Path]:
        """下载微博图片，返回文件路径列表"""
        headers = {"referer": self.get_referer()}
        dirpath = self._get_download_dir(weibo_img_dir)

        async def download_single_image(i: int, img_url: str) -> Path | None:
            """下载单个图片"""
            filename = self._build_download_filename(i, ".jpg")
            filepath = dirpath / filename
            if filepath.exists():
                return filepath
            result_path = await save_img_by_path(
                img_url, filepath, True, headers=headers
            )
            if result_path:
                return result_path
            else:
                sv.logger.error(f"Failed to save image {img_url}")
                return None

        # 并发下载所有图片
        tasks = [
            download_single_image(i, img_url) for i, img_url in enumerate(self.images)
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        saved_images = []
        for result in results:
            if isinstance(result, Path):
                saved_images.append(result)
            elif isinstance(result, Exception):
                sv.logger.error(f"Error in download task: {result}")

        # 处理转发的图片
        if self.repost and self.repost.images:
            repost_images = await self.repost.download_images()
            saved_images.extend(repost_images)

        return saved_images

    async def download_videos(self) -> list[Path]:
        """下载微博视频，返回文件路径列表"""
        headers = {"referer": self.get_referer()}
        dirpath = self._get_download_dir(weibo_video_dir)

        async def download_single_video(i: int, video_url: str) -> Path | None:
            """下载单个视频"""
            try:
                filename = self._build_download_filename(i, ".mp4")
                filepath = dirpath / filename
                if filepath.exists():
                    return filepath
                result_path = await save_video_by_path(
                    video_url, filepath, True, headers=headers
                )
                if result_path:
                    return result_path
                else:
                    sv.logger.error(f"Failed to save video {video_url}")
                    return None
            except Exception as e:
                sv.logger.error(f"Error downloading video {video_url}: {e}")
                return None

        # 并发下载所有视频
        tasks = [
            download_single_video(i, video_url)
            for i, video_url in enumerate(self.videos)
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        saved_videos = []
        for result in results:
            if isinstance(result, Path):
                saved_videos.append(result)
            elif isinstance(result, Exception):
                sv.logger.error(f"Error in download task: {result}")

        # 处理转发的视频
        if self.repost and self.repost.videos:
            repost_videos = await self.repost.download_videos()
            saved_videos.extend(repost_videos)

        return saved_videos

    @override
    async def get_message(
        self,
        full: bool = False,
        with_screenshot: bool = True,
        screenshot_timeout: float = 6.0,
        screenshot_path: Path | None = None,
    ) -> PostMessage:
        image_paths = await self.download_images()
        content = "\n".join(self._build_content_lines())
        header = self._build_text_header()
        if not full:
            schedule_file_cleanup(image_paths)
            return PostMessage(
                text=header,
                images=image_paths,
                content=content,
            )

        ms = None
        video_paths = await self.download_videos()
        screenshot_task = None
        if with_screenshot and not self.description:
            screenshot_task = get_weibo_screenshot_mobile(
                self.url,
                timeout=screenshot_timeout,
                path=screenshot_path,
            )
        elif with_screenshot and self.description == "mapp":
            screenshot_task = get_mapp_weibo_screenshot(
                self.url,
                timeout=screenshot_timeout,
                path=screenshot_path,
            )
        elif with_screenshot and self.description == "desktop":
            screenshot_task = get_weibo_screenshot_desktop(
                self.url,
                timeout=screenshot_timeout,
                path=screenshot_path,
            )

        if screenshot_task:
            try:
                ms = await screenshot_task
                if ms and screenshot_path and screenshot_path.exists():
                    ms = screenshot_path
            except Exception as e:
                sv.logger.error(f"Error fetching screenshot: {e}")
        schedule_file_cleanup(image_paths + video_paths)
        return PostMessage(
            text=header,
            screenshot=ms,
            images=image_paths,
            videos=video_paths,
            content=content,
        )

    @override
    def render_message(
        self, post_message: PostMessage
    ) -> list[Message | MessageSegment]:
        head = post_message.text
        # 有截图时展示截图，无截图时内联正文
        if post_message.screenshot:
            head += "\n" + str(MessageSegment.image(post_message.screenshot))
        elif post_message.content:
            head += "\n" + post_message.content
        tail = self._build_text_tail()
        if tail:
            head += "\n" + tail
        messages: list[Message | MessageSegment] = []
        if head:
            messages.append(Message(head))
        messages.extend(self._build_image_messages(post_message.images))
        messages.extend(
            MessageSegment.video(video_path) for video_path in post_message.videos
        )
        return messages

    def _build_content_lines(self) -> list[str]:
        lines = []
        if self.content:
            lines.append(self.content)
        if self.repost:
            lines.append("------------")
            lines.append("转发自 " + self.repost.nickname)
            lines.append(self.repost.content)
            lines.append("------------")
        return lines

    def _build_text_header(self) -> str:
        if self.nickname:
            return self.nickname + " 微博~"
        return ""

    def _build_text(self, include_content: bool = False) -> str:
        msg = []
        if self.nickname:
            msg.append(self.nickname + " 微博~")
        if include_content:
            content_lines = self._build_content_lines()
            if content_lines:
                msg.append("\n".join(content_lines))
        return "\n".join(msg)

    def _build_text_tail(self) -> str:
        msg = []
        if self.repost and self.repost.url:
            msg.append("源微博详情: " + self.repost.url)
        if self.url:
            msg.append("微博详情: " + self.url)
        return "\n".join(msg)

    def _build_image_messages(
        self,
        image_paths: list[Path],
    ) -> list[Message | MessageSegment]:
        if not image_paths:
            return []

        image_segments = [
            MessageSegment.image(image_path) for image_path in image_paths
        ]
        messages: list[Message | MessageSegment] = []
        num = 4
        for i in (7, 6, 5, 4, 3):
            if len(image_segments) % i == 0:
                num = i
                break
        for i in range(0, len(image_segments), num):
            group = image_segments[i : i + num]
            messages.append(Message(group))
        return messages

    async def _save_avatar_if_needed(self, uid_dir: Path) -> None:
        """每天最多保存一次用户头像"""
        if not self.user_avatar_image:
            return
        avatar_path = uid_dir / "user_avatar.jpg"
        if avatar_path.exists():
            mtime = avatar_path.stat().st_mtime
            if datetime.fromtimestamp(mtime).date() == datetime.now().date():
                return
        try:
            await self._save_resource(self.user_avatar_image, avatar_path)
        except Exception as e:
            sv.logger.warning(f"Failed to save avatar for {self.uid}: {e}")

    async def save(
        self,
        post_message: PostMessage,
    ) -> PostMessage:
        uid_dir = self._get_download_dir(weibo_msg_dir)
        save_dir = uid_dir / self.id
        save_dir.mkdir(parents=True, exist_ok=True)

        await self._save_avatar_if_needed(uid_dir)

        metadata = {
            "uid": self.uid,
            "id": self.id,
            "text": post_message.text,
            "content": post_message.content,
            "url": self.url,
            "nickname": self.nickname,
            "timestamp": self.timestamp,
        }
        (save_dir / "message.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        if post_message.screenshot:
            await self._save_resource(
                post_message.screenshot, save_dir / "screenshot.jpg"
            )

        for index, image in enumerate(post_message.images, start=1):
            await self._save_resource(image, save_dir / "images" / f"{index}.jpg")

        for index, video in enumerate(post_message.videos, start=1):
            await self._save_resource(video, save_dir / "videos" / f"{index}.mp4")

        post_message.images = [save_dir / "images" / f"{i+1}.jpg" for i in range(len(post_message.images))]
        post_message.videos = [save_dir / "videos" / f"{i+1}.mp4" for i in range(len(post_message.videos))]
        if post_message.screenshot:
            post_message.screenshot = save_dir / "screenshot.jpg"
        return post_message

    async def _save_resource(self, resource: bytes | str | Path, target: Path) -> None:
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
                resource, target, True, headers={"referer": self.get_referer()}
            )
        else:
            saved = await save_img_by_path(
                resource, target, True, headers={"referer": self.get_referer()}
            )

        if not saved:
            raise FileNotFoundError(f"failed to save resource: {resource}")


@dataclass
class WeiboDispatchTask:
    """一条微博推送到一个群的任务，共享 post 和 message 引用"""

    post: WeiboPost
    message: PostMessage
    group_id: int

    def get_id(self) -> str:
        return f"{self.group_id}_{self.post.id}"


def adapt_message(
    message: PostMessage,
    group_config: WeiboConfig,
    busy: bool,
) -> PostMessage | None:
    """根据群配置和繁忙状态，从共享 PostMessage 创建适配副本"""
    if group_config.only_pic and not message.images:
        return None

    with_screenshot = bool(group_config.send_screenshot) and not busy
    with_videos = not busy

    return PostMessage(
        text=message.text,
        content=message.content,
        screenshot=message.screenshot if with_screenshot else None,
        images=list(message.images),
        videos=list(message.videos) if with_videos else [],
    )


async def post_msg_from_uid_id(
    uid: str, post_id: str
) -> PostMessage | None:
    msg_dir = weibo_msg_dir / uid / post_id
    if not msg_dir.exists():
        sv.logger.warning(
            f"weibo post not found in cache, refetching: uid={uid} post_id={post_id}"
        )
        post = await parse_weibo_with_id(post_id)
        if not post:
            return None
        return await post.get_message(full=True)

    metadata_path = msg_dir / "message.json"
    metadata: dict = {}
    if metadata_path.exists():
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            sv.logger.warning(
                f"failed to load cached weibo metadata: uid={uid} post_id={post_id} error={e}"
            )

    text = str(metadata.get("text", "") or "")
    content = str(metadata.get("content", "") or "")
    detail_url = f"https://weibo.com/{uid}/{post_id}"
    if detail_url not in text:
        text = "\n".join(part for part in (text, f"微博详情: {detail_url}") if part)
    # 兼容旧存档：旧格式 text 已包含 content，避免重复
    if content and content in text:
        content = ""

    screenshot_path = msg_dir / "screenshot.jpg"
    screenshot = screenshot_path if screenshot_path.exists() else None
    images_dir = msg_dir / "images"
    image_paths = (
        sorted(images_dir.glob("*.jpg"), key=lambda p: p.name)
        if images_dir.exists()
        else []
    )
    videos_dir = msg_dir / "videos"
    video_paths = (
        sorted(videos_dir.glob("*.mp4"), key=lambda p: p.name)
        if videos_dir.exists()
        else []
    )
    return PostMessage(
        text=text,
        screenshot=screenshot,
        images=image_paths,
        videos=video_paths,
        content=content,
    )


wbck = sucmd("weibocookies", aliases={"wbck", "rfwb"})


@wbck.handle()
async def get_weibocookies_cmd():
    try:
        await initialize_weibo_cookies()
        ck = await get_weibocookies()
        if ck:
            await send_to_superuser("Weibo cookies refreshed successfully")
    except:
        sv.logger.error("Failed to initialize or get Weibo cookies")


@on_startup
async def initialize_weibo_cookies():
    ck = await get_weibo_cookies_from_local()
    await save_cookies("weibo", ck)


async def get_weibocookies():
    ck = await get_cookies("weibo")
    return ck


class WeiboRequestError(Exception):
    def __init__(self, message: str, *, reason: str = "", target: str = ""):
        super().__init__(message)
        self.reason = reason
        self.target = target


_missing_weibo_target_queue: asyncio.Queue[str] = asyncio.Queue()
_missing_weibo_target_set: set[str] = set()


def _extract_weibo_target(url: str, params: dict | None = None) -> str:
    if params:
        for key in ("uid", "value", "id"):
            value = params.get(key)
            if value:
                return str(value)

    patterns = [
        r"/u/(\d+)",
        r"[?&]uid=(\d+)",
        r"[?&]value=(\d+)",
        r"[?&]id=([\w-]+)",
        r"/(detail|status)/([\w-]+)",
    ]
    for pattern in patterns:
        matched = re.search(pattern, url)
        if matched:
            return matched.group(matched.lastindex or 1)
    return ""


def _raise_weibo_request_error(
    message: str, *, reason: str = "", target: str = ""
) -> None:
    sv.logger.error(message)
    raise WeiboRequestError(message, reason=reason, target=target)


async def enqueue_missing_weibo_target(target: str) -> bool:
    if not target:
        return False
    if target in _missing_weibo_target_set:
        return False
    _missing_weibo_target_set.add(target)
    await _missing_weibo_target_queue.put(target)
    return True


async def _confirm_missing_weibo_target(target: str) -> bool:
    ck = await get_weibocookies()
    if not ck:
        return False

    try:
        if ck.get("MLOGIN"):
            await _visitor_weibo_module.get_weibo_list(target, 0.0)
        else:
            await _login_weibo_module.get_weibo_list(target, 0.0)
    except WeiboRequestError as e:
        return e.reason == "user_not_found" or e.reason == "account_banned"
    return False


async def process_missing_weibo_target(target: str) -> None:
    from .sub import uid_manager

    confirmed = await _confirm_missing_weibo_target(target)
    if not confirmed:
        sv.logger.info(f"微博账号不存在待删除任务跳过: target={target}, 二次确认未命中")
        return

    deleted_count = remove_subscriptions_by_uid(target)
    if not deleted_count:
        sv.logger.info(f"微博账号不存在待删除任务跳过: target={target}, 数据库中无订阅")
        return

    await uid_manager.remove_uid(target)

    msg = f"微博账号不存在，已自动删除订阅: UID {target}, 共 {deleted_count} 条"
    sv.logger.warning(msg)
    await send_to_superuser(msg)


async def missing_weibo_target_worker() -> None:
    while True:
        try:
            target = _missing_weibo_target_queue.get_nowait()
        except asyncio.QueueEmpty:
            await asyncio.sleep(3)
            continue
        try:
            await process_missing_weibo_target(target)
        except Exception as e:
            sv.logger.error(f"处理微博不存在账号队列失败: target={target}, error: {e}")
        finally:
            _missing_weibo_target_set.discard(target)
            _missing_weibo_target_queue.task_done()


@on_startup
async def start_missing_weibo_target_worker() -> None:
    asyncio.create_task(missing_weibo_target_worker())


def _check_weibo_request_error(
    res: aiohttpx.Response,
    params: dict | None = None,
    *,
    retry_on_ok_minus100: bool = True,
) -> None:
    url = str(res.url)
    target = _extract_weibo_target(url, params)
    target_info = f", target: {target}" if target else ""

    if not res.ok:
        _raise_weibo_request_error(
            f"微博请求失败: status={res.status_code}, url: {url}{target_info}, text: {res.text}",
            reason="http_error",
            target=target,
        )

    try:
        res_data = res.json
    except Exception:
        return

    if not isinstance(res_data, dict):
        return

    ok = res_data.get("ok")
    msg = str(res_data.get("msg", ""))
    data = res_data.get("data", {})

    if ok is None:
        _raise_weibo_request_error(
            f"微博请求失败: 该账号已被封禁或风控, url: {url}{target_info}, text: {res.text}",
            reason="account_banned",
            target=target,
        )

    if ok == -100 and retry_on_ok_minus100:
        _raise_weibo_request_error(
            f"微博请求失败: cookies 可能失效(ok=-100), url: {url}{target_info}, msg: {msg}",
            reason="cookie_invalid",
            target=target,
        )

    if "用户不存在" in msg:
        _raise_weibo_request_error(
            f"微博请求失败: 用户不存在, url: {url}{target_info}, msg: {msg}",
            reason="user_not_found",
            target=target,
        )

    if isinstance(data, dict):
        if "ajax/statuses/mymblog" in url and not data.get("list", []):
            _raise_weibo_request_error(
                f"微博请求失败: 账号暂无数据, url: {url}{target_info}",
                reason="no_data",
                target=target,
            )
        if "api/container/getIndex" in url and not data.get("cards", []):
            _raise_weibo_request_error(
                f"微博请求失败: 账号暂无数据, url: {url}{target_info}",
                reason="no_data",
                target=target,
            )

    if ok in (0, False) and msg:
        _raise_weibo_request_error(
            f"微博请求失败: ok={ok}, url: {url}{target_info}, msg: {msg}",
            reason="api_error",
            target=target,
        )


async def weibo_get(
    url: str,
    *,
    headers: dict | None = None,
    params: dict | None = None,
    cookies: dict | None = None,
    follow_redirects: bool = True,
    timeout: float = 6.0,
    retry_on_ok_minus100: bool = True,
):
    try:
        res = await aiohttpx.get(
            url,
            headers=headers,
            params=params,
            cookies=cookies if cookies else None,
            follow_redirects=follow_redirects,
            timeout=timeout,
        )
    except Exception as e:
        sv.logger.error(f"微博请求异常: url: {url}, params: {params}, error: {e}")
        raise

    _check_weibo_request_error(res, params, retry_on_ok_minus100=retry_on_ok_minus100)
    return res


class _LoginWeiboModule:
    async def get_weibo_list(self, target: str, ts: float = 0.0) -> list[WeiboPost]:
        header = {
            "accept": "application/json, text/plain, */*",
            "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,ja;q=0.7,ko;q=0.6,zh-TW;q=0.5",
            "priority": "u=0, i",
            "sec-ch-ua": '"Chromium";v="141", "Google Chrome";v="141", "Not?A_Brand";v="8"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "navigate",
            "sec-fetch-site": "same-origin",
            "upgrade-insecure-requests": "1",
            "Referer": f"https://weibo.com/u/{target}",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36",
        }
        params = {
            "uid": target,
            "page": 1,
            "feature": 0,
        }
        ck = await get_weibocookies()
        token = ck.get("XSRF-TOKEN", "")
        header["X-Xsrf-Token"] = token
        res = await weibo_get(
            "https://weibo.com/ajax/statuses/mymblog",
            headers=header,
            params=params,
            cookies=ck,
            timeout=6.0,
            retry_on_ok_minus100=True,
        )
        if not res.ok:
            return []
        res_data = res.json
        if not res_data["ok"]:
            return []

        def custom_filter(d) -> bool:
            visible = d.get("visible", {})
            if visible.get("type") not in [0, 6, 7, 8, 9]:
                return False
            user = d.get("user", {})
            if not user or user.get("idstr") != target:
                return False
            created = d["created_at"]
            if created:
                t = datetime.strptime(created, "%a %b %d %H:%M:%S %z %Y").timestamp()
                b = t > ts
            return b

        datalist = res_data.get("data", {}).get("list", [])
        if not datalist:
            return []
        filterlist = list(filter(custom_filter, datalist))
        if not filterlist:
            return []
        postlist = []
        for i in filterlist:
            post = self.parse_weibo_dict(i)
            if not post:
                continue
            postlist.append(post)
        postlist.sort(key=lambda x: x.timestamp, reverse=True)
        return postlist

    async def parse_weibo(self, bid: str) -> WeiboPost | None:
        url = f"https://weibo.com/ajax/statuses/show?id={bid}&locale=zh-CN&isGetLongText=true"
        res = await weibo_get(
            url,
            cookies=await get_weibocookies(),
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
                "Referer": "https://weibo.com/",
            },
            timeout=5.0,
            retry_on_ok_minus100=True,
        )
        rj = res.json
        return self.parse_weibo_dict(rj)

    def parse_weibo_dict(self, rj: dict) -> WeiboPost | None:
        post = self._parse_weibo_dict(rj)
        if not post:
            return None
        if "retweeted_status" in rj:
            if rj["retweeted_status"].get("visible", {}).get("type") == 10:
                return post
            repost = self._parse_weibo_dict(rj["retweeted_status"])
            if repost:
                post.repost = repost
        return post

    def _parse_weibo_dict(self, rj: dict) -> WeiboPost | None:
        user = rj.get("user")
        if not user:
            sv.logger.error(f"获取微博失败: User is None, json: {rj}", color=False)
            return None
        visible = rj.get("visible", {})
        type_ = visible.get("type", 0)
        if type_ not in [0, 6, 7, 8, 9]:
            sv.logger.error(
                f"获取微博失败: visible type {type_} not supported, json: {rj}",
                color=False,
            )
            return None
        description = "" if type_ == 0 else "desktop"
        bid = rj.get("mblogid")
        uid = user.get("idstr")
        nickname = user.get("screen_name")
        avatar_url = user.get("avatar_hd")
        ts = rj["created_at"]
        created_at = datetime.strptime(ts, "%a %b %d %H:%M:%S %z %Y")
        detail_url = f"https://weibo.com/{uid}/{bid}"
        pic_urls = []
        video_urls = []
        if "mix_media_info" in rj:
            pic_urls, video_urls = parse_mix_media_info(rj)
        else:
            pic_info: list = rj.get("pic_infos", {}).values()
            for pic in pic_info:
                pic_url, video_url = parse_pic_info(pic)
                if pic_url:
                    pic_urls.append(pic_url)
                if video_url:
                    video_urls.append(video_url)
            page_info = rj.get("page_info", {})
            if page_info.get("object_type") == "video":
                video_url, pic_url = parse_video_info(page_info)
                if video_url:
                    video_urls.append(video_url)
                if pic_url:
                    pic_urls.append(pic_url)
        post = WeiboPost(
            uid=uid,
            id=bid,
            timestamp=created_at.timestamp(),
            content="",
            url=detail_url,
            images=pic_urls,
            nickname=nickname,
            videos=video_urls,
            description=description,
            user_avatar_image=avatar_url,
        )
        post._get_text(rj["text"])
        return post


class _VisitorWeiboModule:
    async def get_weibo_list(self, target: str, ts: float = 0.0) -> list[WeiboPost]:
        header = {
            "MWeibo-Pwa": "1",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": f"https://m.weibo.cn/u/{target}",
            "sec-fetch-mode": "cors",
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 11_0 like Mac OS X) AppleWebKit/604.1.38 (KHTML, like Gecko) Version/11.0 Mobile/15A372 Safari/604.1",
        }
        container = {"containerid": "107603" + target}
        params = {"type": "uid", "value": target}
        params.update(container)
        ck = await get_weibocookies()
        ok = -404
        res_data = None
        res = await weibo_get(
            "https://m.weibo.cn/api/container/getIndex?",
            headers=header,
            params=params,
            cookies=ck,
            follow_redirects=False,
            timeout=6.0,
            retry_on_ok_minus100=True,
        )
        res_data = res.json
        ok = res_data.get("ok", 0)
        if not res_data:
            return []

        if not res_data["ok"] and res_data["msg"] != "这里还没有内容":
            return []

        def custom_filter(d) -> bool:
            if d.get("mblog") is None:
                return False
            created = d["mblog"]["created_at"]
            if created:
                t = datetime.strptime(created, "%a %b %d %H:%M:%S %z %Y").timestamp()
                b = t > ts
            return d["card_type"] in [9, 6, 7] and b

        def cmp(d1, d2):
            created1 = d1["mblog"]["created_at"]
            created2 = d2["mblog"]["created_at"]
            t1 = datetime.strptime(created1, "%a %b %d %H:%M:%S %z %Y").timestamp()
            t2 = datetime.strptime(created2, "%a %b %d %H:%M:%S %z %Y").timestamp()
            return t1 - t2

        k = functools.cmp_to_key(cmp)
        cards = res_data.get("data", {}).get("cards", [])
        ls = list(filter(custom_filter, cards))
        ls.sort(key=k, reverse=True)
        if not ls:
            return []
        result = []
        for i in ls:
            post = self.parse_weibo_dict(i)
            if not post:
                continue
            if post.timestamp > ts:
                result.append(post)
        return result

    async def parse_weibo(self, id: str) -> WeiboPost | None:
        ts = int(time() * 1000)
        url = "https://m.weibo.cn/statuses/show?id={}&_={}".format(id, ts)
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/ 91.0.4472.124 Safari/537.36",
            "Origin": "https://m.weibo.cn",
            "Referer": "https://m.weibo.cn/detail/{}".format(id),
            "Accept": "application/json, text/plain, */*",
            "x-requested-with": "XMLHttpRequest",
            "mweibo-pwa": "1",
            "sec-fetch-site": "same-origin",
            "sec-fetch-mode": "cors",
            "sec-fetch-dest": "empty",
        }
        res = await weibo_get(
            url,
            follow_redirects=False,
            headers=headers,
            timeout=8.0,
            retry_on_ok_minus100=True,
        )
        if not res.ok:
            return None
        rj: dict = res.json
        if not rj.get("ok", False):
            return None
        rjdata = rj.get("data", {})
        return self.parse_weibo_dict({"mblog": rjdata})

    def parse_weibo_dict(self, raw: dict) -> WeiboPost | None:
        info = raw.get("mblog", {}) if isinstance(raw, dict) else {}
        post = self._parse_weibo_dict(info)
        if not post:
            return None
        if "retweeted_status" in info:
            if info["retweeted_status"].get("visible", {}).get("type") != 0:
                return post
            post.repost = self._parse_weibo_dict(info["retweeted_status"])
        return post

    def _parse_weibo_dict(self, info: dict) -> WeiboPost | None:
        if not info or "user" not in info or "bid" not in info:
            return None
        raw_pics_list = info.get("pics", [])
        video_urls = []
        pic_urls = []
        if isinstance(raw_pics_list, dict):
            for img in raw_pics_list.values():
                if img.get("large"):
                    pic_urls.append(img["large"]["url"])
                elif img.get("videoSrc"):
                    video_urls.append(img["videoSrc"])
        elif isinstance(raw_pics_list, list):
            pic_urls = [img["large"]["url"] for img in raw_pics_list]
            video_urls = [
                img["videoSrc"] for img in raw_pics_list if img.get("videoSrc")
            ]
        else:
            pic_urls = []
        if "page_info" in info and info["page_info"].get("type") == "video":
            page_pic = info["page_info"].get("page_pic")
            if page_pic:
                pic_urls.append(page_pic["url"])
            media = info["page_info"].get("media_info")
            urls = info["page_info"].get("urls")
            video_url = None
            if urls:
                for k in ["mp4_720p_mp4", "mp4_hd_mp4", "mp4_ld_mp4", "mp4_sd_mp4"]:
                    if k in urls:
                        video_url = urls[k]
                        break
            elif media:
                for k in ["stream_url_hd", "stream_url"]:
                    if k in media:
                        video_url = media[k]
                        break
            if video_url:
                video_urls.append(video_url)
        detail_url = f"https://weibo.com/{info['user']['id']}/{info['bid']}"
        ts = info["created_at"]
        created_at = datetime.strptime(ts, "%a %b %d %H:%M:%S %z %Y")
        post = WeiboPost(
            uid=info["user"]["id"],
            id=info["bid"],
            timestamp=created_at.timestamp(),
            content="",
            url=detail_url,
            images=pic_urls,
            nickname=info["user"]["screen_name"],
            videos=video_urls,
        )
        post._get_text(info["text"])
        return post


_login_weibo_module = _LoginWeiboModule()
_visitor_weibo_module = _VisitorWeiboModule()


async def get_weibo_list(
    target: str,
    ts: float = 0.0,
) -> list[WeiboPost]:
    ck = await get_weibocookies()
    if not ck:
        return []
    try:
        if ck.get("MLOGIN"):
            return await _visitor_weibo_module.get_weibo_list(target, ts)
        return await _login_weibo_module.get_weibo_list(target, ts)
    except WeiboRequestError as e:
        if e.reason == "user_not_found" or e.reason == "account_banned":
            await enqueue_missing_weibo_target(target)
        return []


async def get_weibo_new(target: str, ts: float = 0.0) -> WeiboPost | None:
    ls = await get_weibo_list(target, ts)
    return ls[0] if ls else None


async def parse_weibo_with_id(id: str) -> WeiboPost | None:
    ck = await get_weibocookies()
    try:
        if ck:
            if not ck.get("MLOGIN"):
                return await _login_weibo_module.parse_weibo(id)
        return await _visitor_weibo_module.parse_weibo(id)
    except WeiboRequestError as e:
        if e.reason == "user_not_found" or e.reason == "account_banned":
            await enqueue_missing_weibo_target(e.target)
        return None


async def parse_mapp_weibo(url: str) -> WeiboPost | None:
    # what a holyshit,fk weibo
    ## https://mapp.api.weibo.cn/fx/77eaa5c2f741894631a87fc4806a1f05.html
    ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 NetType/WIFI MicroMessenger/7.0.20.1781(0x6700143B) WindowsWechat(0x63090a13) UnifiedPCWindowsWechat(0xf254032b) XWEB/13655 Flue"
    headers = {
        "User-Agent": ua,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "Authority": "mapp.api.weibo.cn",
    }
    ## https://mapp.api.weibo.cn/fx/ed689ab06571073864067e0eeae8de7f.html may redirect to m.weibo.cn
    if furl := await get_redirect(url, headers=headers):
        matched = re.search(r"m.weibo.cn\/(detail|status)\/(\w+)", furl)
        if matched:
            return await parse_weibo_with_id(matched.group(2))
    resp = await weibo_get(
        url,
        headers=headers,
        timeout=8.0,
    )
    text = resp.text
    if not text:
        return None
    soup = BeautifulSoup(text, "lxml")
    imgs = soup.find_all("img", class_="f-bg-imgs")
    parsed_text = ""
    img_urls = []
    video_urls = []
    for img in imgs:
        if img.get("bak_src"):
            img_urls.append(img["data-src"])
        elif img.get("src"):
            img_urls.append(img["src"])
    text_div = soup.find_all("div", class_="weibo-text")
    for div in text_div:
        text = div.get_text(strip=True).replace("&ZeroWidthSpace;", "")
        parsed_text += text + "\n"
    videos = soup.find_all("video", id="video")
    for video in videos:
        if video.get("src"):
            video_urls.append(video["src"])
        if video.get("poster"):
            img_urls.append(video["poster"])
    nickname = ""
    m_text_box = soup.find("div", class_="m-text-box")
    if m_text_box:
        nickname_span = m_text_box.find("span")
        if nickname_span:
            nickname = nickname_span.get_text(strip=True)
        else:
            nickname = ""
    else:
        nickname = ""
    return WeiboPost(
        uid="",
        id="",
        content=parsed_text,
        images=img_urls,
        videos=video_urls,
        url=url,
        nickname=nickname,
        description="mapp",
    )


# 解析图片/视频媒体相关函数


def parse_mix_media_info(dic: dict) -> tuple[list[str], list[str]]:
    pic_urls = []
    video_urls = []
    medias = dic.get("mix_media_info", {}).get("items", [])
    for media in medias:
        mediadata = media.get("data", {})
        if media.get("type") == "pic":
            pic_url, video_url = parse_pic_info(mediadata)
            if pic_url:
                pic_urls.append(pic_url)
            if video_url:
                video_urls.append(video_url)
        elif media.get("type") == "video":
            v_url, p_url = parse_video_info(mediadata)
            if v_url:
                video_urls.append(v_url)
            if p_url:
                pic_urls.append(p_url)
    return pic_urls, video_urls


def parse_pic_info(pic: dict) -> tuple[str, str]:
    pic_url = ""
    video_url = ""
    typ = pic.get("type")
    if vd := pic.get("video") and typ == "livephoto":
        video_url = vd
    for scale in ["largest", "original", "large"]:
        if scale in pic:
            if ur := pic[scale].get("url"):
                pic_url = ur
                break
    return pic_url, video_url


def parse_video_info(page_info: dict) -> tuple[str, str]:
    pic_url = ""
    video_url = ""
    media_info = page_info.get("media_info", {})
    big_pic = media_info.get("big_pic_info", {}).get("pic_big", {}).get("url", "")
    if big_pic:
        pic_url = big_pic
    else:
        pic_url = page_info.get("page_pic", "")
    for k in [
        "mp4_720p_mp4",
        "mp4_hd_url",
        "mp4_sd_url",
        "stream_url_hd",
        "stream_url",
    ]:
        if k in media_info:
            video_url = media_info[k]
            break
    return video_url, pic_url
