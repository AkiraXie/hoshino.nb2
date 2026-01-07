import json
from pathlib import Path
from pydantic import BaseModel
from hoshino import MessageSegment, Message, data_dir
from hoshino.util import aiohttpx, get_cookies, save_video_by_path
import re
from urllib.parse import parse_qs, urlparse
from functools import partial
from hoshino.util import get_redirect
from .sv import sv

xhs_headers = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,"
    "image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/55.0.2883.87 UBrowser/6.2.4098.3 Safari/537.36",
}

xhs_discovery_headers = {
    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) "
    "Version/16.6 Mobile/15E148 Safari/604.1 Edg/132.0.0.0",
    "origin": "https://www.xiaohongshu.com",
    "x-requested-with": "XMLHttpRequest",
    "sec-fetch-site": "same-origin",
    "sec-fetch-mode": "cors",
    "sec-fetch-dest": "empty",
}


get_xhscookies = partial(get_cookies, "xhs")
xhs_dir = data_dir / "xhs"
xhs_dir.mkdir(exist_ok=True)
xhs_img_dir = xhs_dir / "image"
xhs_img_dir.mkdir(exist_ok=True)
xhs_video_dir = xhs_dir / "video"
xhs_video_dir.mkdir(exist_ok=True)


async def parse_xhs(
    url: str,
) -> tuple[list[Message | MessageSegment | str] | None, Path | None]:
    if "xhslink" in url:
        url = await get_redirect(url, xhs_discovery_headers)
    pattern = r"(?:/explore/|/discovery/item/|source=note&noteId=)(\w+)"
    matched = re.search(pattern, url)
    if not matched:
        sv.logger.error(f"Xiaohongshu URL does not match expected pattern,url: {url}")
        return None, None
    xhs_id = matched.group(1)
    parsed_url = urlparse(url)
    urlpath = parsed_url.path
    xhs_id = urlpath.split("/")[-1]
    if urlpath.startswith("/explore/"):
        return await parse_xhs_explore(url, xhs_id)
    elif urlpath.startswith("/discovery/item/"):
        return await parse_xhs_discovery(url, xhs_id)


def xhs_extract_initial_state_json(html: str):
    pattern = r"window\.__INITIAL_STATE__=(.*?)</script>"
    matched = re.search(pattern, html)
    if not matched:
        sv.logger.error("xhs link may be invalid or content has been deleted")
        return None
    json_str = matched.group(1).replace("undefined", "null")
    return json.loads(json_str)


class Stream(BaseModel):
    h264: list[dict] | None = None
    h265: list[dict] | None = None
    av1: list[dict] | None = None
    h266: list[dict] | None = None


class Media(BaseModel):
    stream: Stream


class Video(BaseModel):
    media: Media

    @property
    def video_url(self) -> str | None:
        stream = self.media.stream

        # h264 有水印，h265 无水印
        if stream.h265:
            return stream.h265[0]["masterUrl"]
        elif stream.h264:
            return stream.h264[0]["masterUrl"]
        elif stream.av1:
            return stream.av1[0]["masterUrl"]
        elif stream.h266:
            return stream.h266[0]["masterUrl"]
        return None


async def parse_xhs_explore(url: str, xhs_id: str):
    # params = parse_qs(parsed_url.query)
    # xsec_source = params.get("xsec_source", [None])[0] or "pc_feed"
    # xsec_token = params.get("xsec_token", [None])[0]
    try:
        resp = await aiohttpx.get(
            url,
            headers=xhs_headers,
            cookies=await get_xhscookies(),
        )
    except Exception as e:
        sv.logger.error(f"Error fetching Xiaohongshu data: {e}")
        return None, None
    if not resp.ok:
        sv.logger.error("Error fetching Xiaohongshu data")
        return None, None
    initial_state = xhs_extract_initial_state_json(resp.text)
    if not initial_state:
        sv.logger.error("Xiaohongshu cookies may be invalid")
        return None, None
    note_data = (
        initial_state.get("note", {})
        .get("noteDetailMap", {})
        .get(xhs_id, {})
        .get("note", {})
    )
    if not note_data:
        sv.logger.error("note data not found in Xiaohongshu response")
        return None, None

    class Image(BaseModel):
        urlDefault: str

    class User(BaseModel):
        nickname: str
        avatar: str

    class NoteDetail(BaseModel):
        type: str
        title: str
        desc: str
        user: User
        imageList: list[Image] = []
        video: Video | None = None

        @property
        def nickname(self) -> str:
            return self.user.nickname

        @property
        def avatar_url(self) -> str:
            return self.user.avatar

        @property
        def image_urls(self) -> list[str]:
            return [item.urlDefault for item in self.imageList]

        @property
        def video_url(self) -> str | None:
            if self.type != "video" or not self.video:
                return None
            return self.video.video_url

    notedetail = NoteDetail.parse_obj(note_data)
    title_desc = f"{notedetail.nickname} 小红书笔记~\n{notedetail.title}\n--------\n{notedetail.desc}\n"
    msg = [title_desc, f"笔记链接: {resp.url}"]
    for img_url in notedetail.image_urls:
        msg.append(MessageSegment.image(img_url))
    video_url = notedetail.video_url
    if video_url:
        header = {
            "Referer": "https://www.xiaohongshu.com/",
        }
        path = xhs_video_dir / f"{notedetail.title}_{xhs_id}.mp4"
        path = await save_video_by_path(video_url, path, headers=header)
        res = None
        if not path:
            sv.logger.error("Failed to save video")
            return None, None
        else:
            if path.stat().st_size >= 100 * 1000 * 1000:  # 100MB limit
                res = path
            else:
                msg.append(MessageSegment.video(path))
        return msg, res
    return msg, None


async def parse_xhs_discovery(url: str, xhs_id: str):

    # 疑似可以转成 explore 解析
    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    xsec_source = params.get("xsec_source", [None])[0] or "pc_feed"
    xsec_token = params.get("xsec_token", [None])[0]
    explore_url = f"https://www.xiaohongshu.com/explore/{xhs_id}?xsec_token={xsec_token}&xsec_source={xsec_source}"
    return await parse_xhs_explore(explore_url, xhs_id)


    # class Image(BaseModel):
    #     url: str
    #     urlSizeLarge: str | None = None

    # class User(BaseModel):
    #     nickName: str
    #     avatar: str

    # class NoteData(BaseModel):
    #     type: str
    #     title: str
    #     desc: str
    #     user: User
    #     time: int
    #     lastUpdateTime: int
    #     imageList: list[Image] = []  # 有水印
    #     video: Video | None = None

    #     @property
    #     def image_urls(self) -> list[str]:
    #         return [item.urlSizeLarge or item.url for item in self.imageList]

    #     @property
    #     def video_url(self) -> str | None:
    #         if self.type != "video" or not self.video:
    #             return None
    #         return self.video.video_url

    # class NormalNotePreloadData(BaseModel):
    #     title: str
    #     desc: str
    #     imagesList: list[Image] = []  # 无水印, 但只有一只，用于视频封面

    #     @property
    #     def image_urls(self) -> list[str]:
    #         return [item.urlSizeLarge or item.url for item in self.imagesList]


    # class NoteDataWrapper(BaseModel):
    #     noteData: NoteData


    # class NoteDataContainer(BaseModel):
    #     data: NoteDataWrapper
    #     normalNotePreloadData: NormalNotePreloadData | None = None


    # class InitialState(BaseModel):
    #     noteData: NoteDataContainer
    # try:
    #     resp = await aiohttpx.get(
    #         url,
    #         headers=xhs_discovery_headers,
    #         follow_redirects=True,
    #       cookies = await get_xhscookies()
    #     )
    # except Exception as e:
    #     sv.logger.error(f"Error fetching Xiaohongshu data: {e}")
    #     return None, None
    # if not resp.ok:
    #     sv.logger.error("Error fetching Xiaohongshu data")
    #     return None, None
    # html = resp.text
    # initial_state = xhs_extract_initial_state_json(html)
    # if not initial_state:
    #     return None, None
    # initial_state = InitialState.parse_obj(initial_state)
    # notedata = initial_state.noteData
    # if not notedata:
    #     sv.logger.error("note data not found in Xiaohongshu response")
    #     return None, None
    # preload_data = notedata.normalNotePreloadData
    # note_data = notedata.data.noteData
    # if not note_data:
    #     sv.logger.error("note data not found in Xiaohongshu response")
    #     return None, None
    # username = note_data.user.nickName
    # title_desc = (
    #     f"{username} 小红书笔记~\n{note_data.title}\n--------\n{note_data.desc}\n"
    # )
    # msg = [title_desc, f"笔记链接: {url}"]
    # if video_url := note_data.video_url:
    #     if preload_data:
    #         preloaddata = NormalNotePreloadData.parse_obj(preload_data)
    #     for i in preloaddata.image_urls:
    #         msg.append(MessageSegment.image(i))
    #     header = {
    #         "Referer": "https://www.xiaohongshu.com/",
    #     }
    #     path = xhs_video_dir / f"{note_data.title}_{note_data.time}.mp4"
    #     path = await save_video_by_path(video_url, path, headers=header)
    #     res = None
    #     if not path:
    #         sv.logger.error("Failed to save video")
    #         return None, None
    #     else:
    #         if path.stat().st_size >= 100 * 1000 * 1000:  # 100MB limit
    #             res = path
    #         else:
    #             msg.append(MessageSegment.video(path))
    #     return msg, res
    # elif img_urls := note_data.image_urls:
    #     for img_url in img_urls:
    #         msg.append(MessageSegment.image(img_url))
    # return msg, None
