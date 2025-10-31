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
import asyncio
from pathlib import Path
from pydantic import BaseModel, Field
from typing import Any, List, Optional, Self
import re
from hoshino.util import aiohttpx,get_redirect, save_img_by_path, save_video_by_path
from hoshino import data_dir
from ..utils import Post as BasePost, clean_filename
from .data import sv
from hoshino import Message, MessageSegment
douyin_img_dir = data_dir / "douyinimages"
douyin_img_dir.mkdir(exist_ok=True)
douyin_video_dir = data_dir / "douyinvideos"
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
                result_path = await save_img_by_path(
                    img_url, filepath, True
                )
                if result_path:
                    return result_path
                else:
                    sv.logger.error(f"Failed to save image {img_url}")
                    return None
            except Exception as e:
                sv.logger.error(f"Error downloading image {img_url}: {e}")
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

        return saved_images

    async def download_videos(self) -> list[Path]:

        async def download_single_video(i: int, video_url: str) -> Path | None:
            """下载单个视频"""
            try:
                content_part = clean_filename(self.content[:12])
                nickname_part = clean_filename(self.nickname)
                filename = f"{content_part}_{nickname_part}_{self.id}_{i}.mp4"
                filepath = douyin_video_dir / filename
                result_path = await save_video_by_path(
                    video_url, filepath, True
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

        return saved_videos
    async def get_referer(self) -> str:
        return "https://douyin.com/"

    async def get_message(self, with_screenshot: bool=False) -> list[Message | MessageSegment]:
        imgs = await self.download_images()
        vids = await self.download_videos()
        cnt = self.content or ""
        msg = [f"{self.nickname} 抖音~\n---------\n{cnt}"]
        msg.append(f"抖音链接: {self.url}")
        msg.extend(MessageSegment.image(img) for img in imgs)
        msg.extend(MessageSegment.video(vid) for vid in vids)
        return msg

class PlayAddr(BaseModel):
    url_list: List[str]


class Cover(BaseModel):
    url_list: List[str]


class Video(BaseModel):
    play_addr: PlayAddr
    cover: Cover


class Image(BaseModel):
    video: Optional[Video] = None
    url_list: List[str] = Field(default_factory=list)


class ShareInfo(BaseModel):
    share_desc_info: str


class Author(BaseModel):
    nickname: str


class SlidesData(BaseModel):
    author: Author
    share_info: ShareInfo
    images: List[Image]

    @property
    def images_urls(self) -> List[str]:
        return [image.url_list[0] for image in self.images]

    @property
    def dynamic_urls(self) -> List[str]:
        return [image.video.play_addr.url_list[0] for image in self.images if image.video]


class SlidesInfo(BaseModel):
    aweme_details: List[SlidesData] = Field(default_factory=list)


class VideoData(BaseModel):
    author: Author
    desc: str
    images: Optional[List[Image]] = None
    video: Optional[Video] = None

    @property
    def images_urls(self) -> Optional[List[str]]:
        return [image.url_list[0] for image in self.images] if self.images else None

    @property
    def video_url(self) -> Optional[str]:
        return self.video.play_addr.url_list[0].replace("playwm", "play") if self.video else None

    @property
    def cover_url(self) -> Optional[str]:
        return self.video.cover.url_list[0] if self.video else None


class VideoInfoRes(BaseModel):
    item_list: List[VideoData] = Field(default_factory=list)

    @property
    def video_data(self) -> VideoData | None:
        if not self.item_list:
            return None
        return self.item_list[0]


class VideoOrNotePage(BaseModel):
    videoInfoRes: VideoInfoRes


class LoaderData(BaseModel):
    video_page: Optional[VideoOrNotePage] = Field(alias="video_(id)/page", default=None)
    note_page: Optional[VideoOrNotePage] = Field(alias="note_(id)/page", default=None)


class RouterData(BaseModel):
    loaderData: LoaderData
    errors: Optional[dict[str, Any]] = None

    @property
    def video_data(self) -> VideoData | None:
        if page := self.loaderData.video_page:
            return page.videoInfoRes.video_data
        elif page := self.loaderData.note_page:
            return page.videoInfoRes.video_data
        return None


class DouyinParser:
    def __init__(self):
        self.ios_headers = IOS_HEADER.copy()
        self.android_headers = {"Accept": "application/json, text/plain, */*", **ANDROID_HEADER}

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
        for url in [
            self._build_m_douyin_url(_type, video_id),
            share_url,
            iesdouyin_url,
        ]:
            return await self.parse_video(url, video_id)

    async def parse_video(self, url: str, vid: str = "") -> Post | None:
        response = await aiohttpx.get(url, headers=self.ios_headers, verify=False, follow_redirects=False)
        if response.status_code != 200:
            sv.logger.error(f"douyin 请求失败，状态码 {response.status_code}")
        text = response.text

        video_data = self._extract_data(text)
        videos = [video_data.video_url]
        images = video_data.images_urls if video_data.images_urls else []
        images.append(video_data.cover_url)
        return Post(
            content=video_data.desc,
            images=images,
            nickname=video_data.author.nickname,
            videos=videos,
            id=vid,
            url=url,
            uid=video_data.author.nickname
        )

    def _extract_data(self, text: str) -> "VideoData":
        """从html中提取视频数据

        Args:
            text (str): 网页源码

        Raises:
            ParseException: 解析失败

        Returns:
            VideoData: 数据
        """
        pattern = re.compile(
            pattern=r"window\._ROUTER_DATA\s*=\s*(.*?)</script>",
            flags=re.DOTALL,
        )
        matched = pattern.search(text)
        c = matched.group(1).strip()
        if not matched or not matched.group(1):
           sv.logger.error("douyin: 无法从网页中提取数据")
           return None
        return RouterData.parse_raw(c).video_data

    async def parse_slides(self, video_id: str) -> Post | None:
        url = "https://www.iesdouyin.com/web/api/v2/aweme/slidesinfo/"
        params = {
            "aweme_ids": f"[{video_id}]",
            "request_source": "200",
        }
        response = await aiohttpx.get(url, params=params, headers=self.android_headers,verify=False)
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
            uid=slides_data.author.nickname
        )