import json
from pathlib import Path

from pydantic import BaseModel
from hoshino import MessageSegment, Message, data_dir
from hoshino.service import Service
from ..utils import Post
from hoshino.util import aiohttpx, get_cookies, save_img_by_path, save_video_by_path
from time import strftime, localtime
import re
from urllib.parse import parse_qs, urlparse
from functools import partial
from ..bilireq.utils import BiliBiliDynamic
from hoshino.util import get_redirect



sv = Service("resolve")

bili_headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
}
bili_video_pat = re.compile(r"bilibili.com/video/(BV[A-Za-z0-9]{10})")

dyn_url = "https://api.bilibili.com/x/polymer/web-dynamic/v1/detail"

get_xhscookies = partial(get_cookies, "xhs")
xhs_dir = data_dir / "xhs"
xhs_dir.mkdir(exist_ok=True)
xhs_img_dir = xhs_dir / "image"
xhs_img_dir.mkdir(exist_ok=True)
xhs_video_dir = xhs_dir / "video"
xhs_video_dir.mkdir(exist_ok=True)


async def get_dynamic_from_url(url: str) -> BiliBiliDynamic | None:
    if "t.bilibili.com" in url or "/opus" in url:
        matched = re.search(r"/(\d+)", url)
        if matched:
            uid = matched.group(1)
            params = {
                "timezone_offset": -480,
                "id": uid,
                "features": "itemOpusStyle,opusBigCover,onlyfansVote,endFooterHidden,decorationCard,onlyfansAssetsV2,ugcDelete,onlyfansQaCard,commentsNewVersion",
            }
            resp = await aiohttpx.get(
                dyn_url,
                params=params,
                cookies=await get_cookies("bilibili"),
                headers=bili_headers,
            )
            if resp.ok:
                data = resp.json.get("data", {})
                if not data:
                    return None
                card = data.get("item", {})
                if not card:
                    return None
                dyn = BiliBiliDynamic.from_dict(card)
                return dyn
    return None


async def get_bvid(url: str) -> str | None:
    if loc := await get_redirect(url):
        if mat := bili_video_pat.search(loc):
            return mat.group(1)
        else:
            return None
    return None


# 处理超过一万的数字
def handle_num(num: int) -> str:
    if num > 10000:
        s = f"{(num / 10000.0):.2f}万"
    else:
        s = str(num)
    return s


async def get_bili_video_resp(bvid: str = "", avid: str = "") -> Message | None:
    url = "https://api.bilibili.com/x/web-interface/view"
    if avid:
        url = f"https://api.bilibili.com/x/web-interface/view?aid={avid}"
    else:
        url = f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}"
    try:
        resp = await aiohttpx.get(url, headers=bili_headers)
    except Exception:
        return None
    js = resp.json
    res = js.get("data")
    if not res:
        return None

    pubdate = strftime("%Y-%m-%d %H:%M:%S", localtime(res["pubdate"]))
    msg = []
    msg.append(str(MessageSegment.image(res["pic"])))
    msg.append(f"标题：{res['title']}")
    msg.append(f"类型：{res['tname']} | UP: {res['owner']['name']} | 日期：{pubdate}")
    msg.append(
        f"播放：{handle_num(res['stat']['view'])} | 弹幕：{handle_num(res['stat']['danmaku'])} | 收藏：{handle_num(res['stat']['favorite'])}"
    )
    msg.append(f"链接: https://www.bilibili.com/video/av{res['aid']}")
    return Message("\n".join(msg))


xhs_headers = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,"
            "image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/55.0.2883.87 UBrowser/6.2.4098.3 Safari/537.36"
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
    if urlpath.startswith("/explore/"):
        xhs_id = urlpath.split("/")[-1]
        return await parse_xhs_explore(url, xhs_id)
    elif urlpath.startswith("/discovery/item/"):
        return await parse_xhs_discovery(url)

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



async def parse_xhs_explore(url:str,xhs_id:str):



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
    note_data = initial_state.get("note", {}).get("noteDetailMap", {}).get(xhs_id, {}).get("note", {})
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


async def parse_xhs_discovery(url:str):
    try:
        resp = await aiohttpx.get(
            url,
            headers=xhs_discovery_headers,
            cookies=await get_xhscookies(),
        )
    except Exception as e:
        sv.logger.error(f"Error fetching Xiaohongshu data: {e}")
        return None, None
    if not resp.ok:
        sv.logger.error("Error fetching Xiaohongshu data")
        return None, None
    html = resp.text
    initial_state = xhs_extract_initial_state_json(html)
    if not initial_state:
        sv.logger.error("Xiaohongshu cookies may be invalid")
        return None, None
    note_data = initial_state.get("noteData")
    if not note_data:
        sv.logger.error("note data not found in Xiaohongshu response")
        return None, None
    preload_data = note_data.get("normalNotePreloadData", {})
    note_data = note_data.get("data", {}).get("noteData", {})
    if not note_data:
        sv.logger.error("note data not found in Xiaohongshu response")
        return None, None
    class Image(BaseModel):
        url: str
        urlSizeLarge: str | None = None

    class User(BaseModel):
        nickName: str
        avatar: str

    class NoteData(BaseModel):
        type: str
        title: str
        desc: str
        user: User
        time: int
        lastUpdateTime: int
        imageList: list[Image] = []  # 有水印
        video: Video | None = None

        @property
        def image_urls(self) -> list[str]:
            return [item.url for item in self.imageList]

        @property
        def video_url(self) -> str | None:
            if self.type != "video" or not self.video:
                return None
            return self.video.video_url

    class NormalNotePreloadData(BaseModel):
        title: str
        desc: str
        imagesList: list[Image] = []  # 无水印, 但只有一只，用于视频封面

        @property
        def image_urls(self) -> list[str]:
            return [item.urlSizeLarge or item.url for item in self.imagesList]

    notedetail = NoteData.parse_obj(note_data)
    username = notedetail.user.nickName
    title_desc = f"{username} 小红书笔记~\n{notedetail.title}\n--------\n{notedetail.desc}\n"
    msg = [title_desc, f"笔记链接: {url}"]
    video_url = notedetail.video_url
    if video_url:
        if preload_data:
            preloaddata = NormalNotePreloadData.parse_obj(preload_data)
            for i in preloaddata.image_urls:
                msg.append(MessageSegment.image(i))
        else:
            for img_url in notedetail.image_urls:
                msg.append(MessageSegment.image(img_url))
        header = {
            "Referer": "https://www.xiaohongshu.com/",
        }
        path = xhs_video_dir / f"{notedetail.title}_{notedetail.time}.mp4"
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
    else:
        for img_url in notedetail.image_urls:
            msg.append(MessageSegment.image(img_url))
    return msg, None