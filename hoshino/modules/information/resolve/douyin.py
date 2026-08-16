import asyncio
import re
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from pydantic import BaseModel, Field, ValidationError

from hoshino import data_dir
from hoshino.command import uni_image, uni_text, uni_video
from hoshino.core.hooks import on_post_startup
from hoshino.types import MessageLike
from hoshino.util import aiohttpx
from hoshino.util.media import save_img_by_path, save_video_by_path
from hoshino.util.message import send_segments
from hoshino.util.network import get_redirect

from ..utils import Post as BasePost
from ..utils import PostMessage, clean_filename
from .sv import sv

COMMON_HEADER = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/55.0.2883.87 UBrowser/6.2.4098.3 Safari/537.36"
}

IOS_HEADER = {
    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) "
    "Version/16.6 Mobile/15E148 Safari/604.1 Edg/132.0.0.0"
}

ANDROID_HEADER = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 15; SM-G998B) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/132.0.0.0 Mobile Safari/537.36 Edg/132.0.0.0"
}

# 抖音分享页默认校验证书；若运行环境证书校验失败（上游反爬/代理环境），
# 可改为 False 关闭校验以恢复可用。
DOUYIN_VERIFY_SSL = True
# 匿名 ttwid 注册端点：分享页 SSR 是否内嵌 videoInfoRes 取决于请求是否带 ttwid
# cookie（无 cookie 时页面只渲染 ua/itemId/abParams 等配置壳，参见 astrbot_plugin_parser）。
TTWID_REGISTER_URL = "https://ttwid.bytedance.com/ttwid/union/register/"
# 播放端点清晰度候选：按文件大小挑最大可用（无水印，来源同 astrbot_plugin_parser）。
PLAY_RATIOS = ("1080p", "720p", "540p", "360p")
douyin_img_dir = data_dir / "douyinimages"
douyin_video_dir = data_dir / "douyinvideos"
douyin_img_dir.mkdir(exist_ok=True)
douyin_video_dir.mkdir(exist_ok=True)


class Post(BasePost):
    async def download_images(self) -> list[Path]:
        async def download_single_image(i: int, img_url: str) -> Path | None:
            """下载单个图片"""
            try:
                content_part = clean_filename(self.content[:20])
                nickname_part = clean_filename(self.nickname)
                filename = f"{content_part}_{nickname_part}_{self.id}_{i}.jpg"
                filepath = douyin_img_dir / filename
                result_path = await save_img_by_path(img_url, filepath, True)
                if result_path:
                    return result_path
                sv.logger.error(f"Failed to save image {img_url}")
                return None
            except Exception:
                sv.logger.exception(f"Error downloading image {img_url}", exception=True)
                return None

        # 并发下载所有图片
        tasks = [download_single_image(i, img_url) for i, img_url in enumerate(self.images)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        saved_images = []
        for result in results:
            if isinstance(result, Path):
                saved_images.append(result)
            elif isinstance(result, Exception):
                sv.logger.error(f"Error in download task: {result}")

        return saved_images

    async def download_videos(self) -> list[Path]:
        async def download_single_video(i: int, video_url: str) -> Path | None:
            """下载单个视频"""
            try:
                content_part = clean_filename(self.content[:12])
                nickname_part = clean_filename(self.nickname)
                filename = f"{content_part}_{nickname_part}_{self.id}_{i}.mp4"
                filepath = douyin_video_dir / filename
                result_path = await save_video_by_path(video_url, filepath, True)

                if result_path:
                    return result_path
                sv.logger.error(f"Failed to save video {video_url}")
                return None
            except Exception:
                sv.logger.exception(f"Error downloading video {video_url}", exception=True)
                return None

        # 并发下载所有视频
        tasks = [download_single_video(i, video_url) for i, video_url in enumerate(self.videos)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        saved_videos = []
        for result in results:
            if isinstance(result, Path):
                saved_videos.append(result)
            elif isinstance(result, Exception):
                sv.logger.error(f"Error in download task: {result}")

        return saved_videos

    async def get_referer(self) -> str:
        return "https://douyin.com/"

    async def get_message(self, full: bool = False) -> PostMessage:
        imgs = await self.download_images()
        vids: list[Path] = []
        if full:
            vids = await self.download_videos()
        return PostMessage(
            text=self._build_text(),
            images=imgs,
            videos=vids,
        )

    def render_message(self, post_message: PostMessage) -> list[MessageLike]:
        messages: list[MessageLike] = []
        if post_message.text:
            messages.append(uni_text(post_message.text))
        messages.extend(uni_image(img) for img in post_message.images)
        messages.extend(uni_video(vid) for vid in post_message.videos)
        return messages

    def _build_text(self) -> str:
        cnt = self.content or ""
        return f"{self.nickname} 抖音~\n---------\n{cnt}\n抖音链接: {self.url}"


class PlayAddr(BaseModel):
    uri: str | None = None
    url_list: list[str] = Field(default_factory=list)


class Cover(BaseModel):
    url_list: list[str]


class Video(BaseModel):
    play_addr: PlayAddr
    cover: Cover


class Image(BaseModel):
    video: Video | None = None
    url_list: list[str] = Field(default_factory=list)


class ShareInfo(BaseModel):
    share_desc_info: str


class Author(BaseModel):
    nickname: str


class SlidesData(BaseModel):
    author: Author
    share_info: ShareInfo
    images: list[Image]

    @property
    def images_urls(self) -> list[str]:
        return [next(iter(image.url_list), "") for image in self.images]

    @property
    def dynamic_urls(self) -> list[str]:
        return [
            next(iter(image.video.play_addr.url_list), "") for image in self.images if image.video
        ]


class SlidesInfo(BaseModel):
    aweme_details: list[SlidesData] = Field(default_factory=list)


class VideoData(BaseModel):
    author: Author
    desc: str
    images: list[Image] | None = None
    video: Video | None = None

    @property
    def images_urls(self) -> list[str] | None:
        return [image.url_list[0] for image in self.images] if self.images else None

    @property
    def video_url(self) -> str | None:
        return self.video.play_addr.url_list[0].replace("playwm", "play") if self.video else None

    @property
    def play_token(self) -> str | None:
        """播放端点 token：优先 play_addr.uri，回退从 url_list 的 video_id 参数提取。"""
        if not self.video:
            return None
        if self.video.play_addr.uri:
            return self.video.play_addr.uri
        for url in self.video.play_addr.url_list:
            query = parse_qs(urlparse(url).query)
            if video_id := query.get("video_id"):
                return video_id[0]
        return None

    @property
    def cover_url(self) -> str | None:
        return self.video.cover.url_list[0] if self.video else None


class VideoInfoRes(BaseModel):
    item_list: list[VideoData] = Field(default_factory=list)

    @property
    def video_data(self) -> VideoData | None:
        if not self.item_list:
            return None
        return self.item_list[0]


class VideoOrNotePage(BaseModel):
    videoInfoRes: VideoInfoRes


class LoaderData(BaseModel):
    video_page: VideoOrNotePage | None = Field(alias="video_(id)/page", default=None)
    note_page: VideoOrNotePage | None = Field(alias="note_(id)/page", default=None)


class RouterData(BaseModel):
    loaderData: LoaderData
    errors: dict[str, Any] | None = None

    @property
    def video_data(self) -> VideoData | None:
        if (page := self.loaderData.video_page) or (page := self.loaderData.note_page):
            return page.videoInfoRes.video_data
        return None


class DouyinParser:
    def __init__(self):
        self.ios_headers = IOS_HEADER.copy()
        self.android_headers = {
            "Accept": "application/json, text/plain, */*",
            **ANDROID_HEADER,
        }
        # 匿名 ttwid cookie（"ttwid=<value>"），进程内缓存；失效时重新注册。
        self._ttwid: str | None = None

    def _build_iesdouyin_url(self, _type: str, video_id: str) -> str:
        return f"https://www.iesdouyin.com/share/{_type}/{video_id}"

    def _build_m_douyin_url(self, _type: str, video_id: str) -> str:
        return f"https://m.douyin.com/share/{_type}/{video_id}"

    async def parse_share_url(self, share_url: str) -> Post | None:
        if matched := re.match(r"(video|note)/([0-9]+)", share_url):
            # https://www.douyin.com/video/xxxxxx
            _type, video_id = matched.group(1), matched.group(2)
            iesdouyin_url = self._build_iesdouyin_url(_type, video_id)
        else:
            # https://v.douyin.com/xxxxxx
            iesdouyin_url = await get_redirect(share_url)
            # https://www.iesdouyin.com/share/video/7468908569061100857/?region=CN&mid=0&u_
            matched = re.search(r"(slides|video|note)/(\d+)", iesdouyin_url)
            if not matched:
                sv.logger.error(f"douyin URL does not match expected pattern,url: {share_url}")
                return None
            _type, video_id = matched.group(1), matched.group(2)
            if _type == "slides":
                return await self.parse_slides(video_id)
        # 原 for+return 等价于只尝试第一个候选地址（后续地址不会回退），直接调用
        return await self.parse_video(self._build_m_douyin_url(_type, video_id), video_id)

    async def ensure_ttwid(self) -> str | None:
        """注册并缓存匿名 ttwid cookie；失败返回 None（调用方降级为无 cookie 请求）。

        分享页 SSR 是否内嵌 videoInfoRes 取决于请求带不带 ttwid：无 cookie 时
        页面只渲染 ua/itemId/abParams 等配置壳。注册流程：POST union/register
        拿到 redirect_url，再 GET 回调让服务端下发 ttwid cookie。
        """
        if self._ttwid:
            return self._ttwid
        payload = {
            "region": "cn",
            "aid": 1768,
            "needFid": False,
            "service": "www.iesdouyin.com",
            "union": True,
            "fid": "",
        }
        headers = {
            **self.ios_headers,
            "Content-Type": "application/json",
            "Referer": "https://www.iesdouyin.com/",
        }
        try:
            response = await aiohttpx.post(
                TTWID_REGISTER_URL,
                json=payload,
                headers=headers,
                verify=DOUYIN_VERIFY_SSL,
                timeout=10.0,
            )
            if response.status_code >= 400:
                sv.logger.error(f"douyin: ttwid 注册失败，状态码 {response.status_code}")
                return None
            ttwid = self._ttwid_from_cookies(response.headers)
            body = response.json
            if isinstance(body, dict) and (callback_url := body.get("redirect_url")):
                callback = await aiohttpx.get(
                    callback_url,
                    headers={**self.ios_headers, "Referer": "https://www.iesdouyin.com/"},
                    verify=DOUYIN_VERIFY_SSL,
                    follow_redirects=False,
                    timeout=10.0,
                )
                if not ttwid:
                    ttwid = self._ttwid_from_cookies(callback.headers)
        except Exception as exc:
            sv.logger.error(f"douyin: ttwid 注册异常: {type(exc).__name__}")
            return None
        if not ttwid:
            sv.logger.error("douyin: ttwid 注册成功但未拿到 cookie")
            return None
        self._ttwid = ttwid
        sv.logger.info("douyin: ttwid 注册成功")
        return ttwid

    @staticmethod
    def _ttwid_from_cookies(headers: Any) -> str | None:
        """从 Set-Cookie 头提取 ttwid（保留原始编码，含 %7C 等）。"""
        for value in headers.get_list("set-cookie"):
            if value.startswith("ttwid="):
                return value.split(";", 1)[0]
        return None

    async def parse_video(self, url: str, vid: str = "") -> Post | None:
        video_data = None
        for _ in range(2):
            headers = self.ios_headers
            ttwid = await self.ensure_ttwid()
            if ttwid:
                headers = {**self.ios_headers, "Cookie": ttwid}
            response = await aiohttpx.get(
                url,
                headers=headers,
                verify=DOUYIN_VERIFY_SSL,
                follow_redirects=False,
            )
            if response.status_code != 200:
                sv.logger.error(f"douyin 请求失败，状态码 {response.status_code}")
                return None

            video_data = self._extract_data(response.text)
            if video_data is not None or not ttwid:
                break
            # 带 ttwid 仍解析不出（cookie 失效/布局变化）→ 重新注册再试一次。
            sv.logger.warning("douyin: 带 ttwid 解析失败，重新注册后重试")
            self._ttwid = None
        if video_data is None:
            sv.logger.error(f"douyin: 解析视频数据失败，url: {url}")
            return None

        play_url = await self._resolve_play_url(video_data, url)
        videos = [play_url] if play_url else []
        images = list(video_data.images_urls or [])
        if video_data.cover_url:
            images.append(video_data.cover_url)
        return Post(
            content=video_data.desc,
            images=images,
            nickname=video_data.author.nickname,
            videos=videos,
            id=vid,
            url=url,
            uid=video_data.author.nickname,
        )

    async def _resolve_play_url(self, video_data: "VideoData", referer: str) -> str | None:
        """优先经 aweme play 端点探测最高可用清晰度（无水印），失败回退 playwm→play。"""
        if video_data.video and (token := video_data.play_token):
            best: tuple[int, str] | None = None
            for ratio in PLAY_RATIOS:
                play_url = f"https://aweme.snssdk.com/aweme/v1/play/?video_id={token}&ratio={ratio}"
                try:
                    response = await aiohttpx.get(
                        play_url,
                        headers={**self.ios_headers, "Range": "bytes=0-1", "Referer": referer},
                        verify=DOUYIN_VERIFY_SSL,
                        follow_redirects=True,
                        timeout=10.0,
                    )
                except Exception as exc:
                    sv.logger.debug(f"douyin: play 探测失败 ratio={ratio}: {type(exc).__name__}")
                    continue
                if response.status_code >= 400:
                    continue
                size = self._response_size(response.headers)
                if size > 0 and (best is None or size > best[0]):
                    best = (size, str(response.url))
            if best:
                sv.logger.info(f"douyin: play 端点探测成功，{best[0]} bytes")
                return best[1]
        return video_data.video_url

    @staticmethod
    def _response_size(headers: Any) -> int:
        """从 Content-Range/Content-Length 提取文件大小。"""
        if (content_range := headers.get("Content-Range")) and (
            matched := re.search(r"/(\d+)\s*$", content_range)
        ):
            return int(matched.group(1))
        if content_length := headers.get("Content-Length"):
            try:
                return int(content_length)
            except ValueError:
                return 0
        return 0

    def _extract_data(self, text: str) -> "VideoData | None":
        """从 html 中提取视频数据

        Args:
            text (str): 网页源码

        Returns:
            VideoData | None: 解析出的数据；反爬页等无法解析时返回 None
        """
        pattern = re.compile(
            pattern=r"window\._ROUTER_DATA\s*=\s*(.*?)</script>",
            flags=re.DOTALL,
        )
        matched = pattern.search(text)
        if not matched or not matched.group(1):
            sv.logger.error("douyin: 无法从网页中提取数据")
            return None
        # 抖音 SSR 布局会不定期变化（如 loaderData.video_(id)/page 不再携带
        # videoInfoRes）；结构不符时按反爬页处理，返回 None 而不是抛异常。
        try:
            return RouterData.model_validate_json(matched.group(1).strip()).video_data
        except ValidationError:
            sv.logger.error("douyin: _ROUTER_DATA 结构与预期不符，无法解析视频数据")
            return None

    async def parse_slides(self, video_id: str) -> Post | None:
        url = "https://www.iesdouyin.com/web/api/v2/aweme/slidesinfo/"
        params = {
            "aweme_ids": f"[{video_id}]",
            "request_source": "200",
        }
        response = await aiohttpx.get(
            url,
            params=params,
            headers=self.android_headers,
            verify=DOUYIN_VERIFY_SSL,
        )
        if response.status_code != 200:
            sv.logger.error(f"douyin 请求失败，状态码 {response.status_code}")
            return None

        slides_data = SlidesInfo.parse_raw(response.text).aweme_details[0]

        return Post(
            content=slides_data.share_info.share_desc_info,
            nickname=slides_data.author.nickname,
            images=slides_data.images_urls,
            videos=slides_data.dynamic_urls,
            url=f"https://www.iesdouyin.com/share/slides/{video_id}",
            id=video_id,
            uid=slides_data.author.nickname,
        )


dparser = DouyinParser()


@on_post_startup
async def _prefetch_ttwid() -> None:
    """启动后预取匿名 ttwid 并放内存，避免首次解析才注册（非阻塞，失败不阻断）。"""
    if await dparser.ensure_ttwid():
        sv.logger.info("douyin: 启动时 ttwid 已就绪")
    else:
        sv.logger.warning("douyin: 启动时 ttwid 预取失败，首次解析时会惰性重试")


async def resolve_douyin(name: str, url: str) -> bool:
    post = await dparser.parse_share_url(url)
    if not post:
        sv.logger.error(f"{name} parse error")
        return False
    post_message = await post.get_message(full=True)
    msgs = post.render_message(post_message)
    if not msgs:
        return False
    await asyncio.sleep(0.3)
    await send_segments(msgs)
    return True
