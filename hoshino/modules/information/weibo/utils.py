from dataclasses import dataclass
from datetime import datetime
import asyncio
import functools
import os
from pathlib import Path
import re
from typing import override
from urllib.parse import unquote
from bs4 import BeautifulSoup
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from sqlalchemy.types import Float, Integer, Text
from time import time
from hoshino import db_dir, Message, Service, MessageSegment, config
from hoshino.util import (
    aiohttpx,
    get_cookies,
    get_redirect,
    save_video_by_path,
    save_img_by_path,
)
from .pw import (
    get_mapp_weibo_screenshot,
    get_weibo_cookies_from_local,
    get_weibo_screenshot_mobile,
    get_weibo_screenshot_desktop,
    get_weibo_visitor_cookies,
)
from hoshino import on_startup

from ..utils import Post, clean_filename
from hoshino.util import save_cookies

sv = Service("weibo", enable_on_default=False, visible=False)

db_path = os.path.join(db_dir, "weibodata.db")
weibo_img_dir = config.data_dir / "weiboimages"
weibo_img_dir.mkdir(parents=True, exist_ok=True)
weibo_video_dir = config.data_dir / "weibovideos"
weibo_video_dir.mkdir(parents=True, exist_ok=True)

engine = create_engine(f"sqlite:///{db_path}", echo=False, future=True)
Session = sessionmaker(bind=engine, expire_on_commit=False)


@dataclass
class WeiboPost(Post):
    """微博POST数据类"""

    group_id: str = ""

    @override
    def get_referer(self) -> str:
        """获取微博的referer"""
        return "https://weibo.com"

    async def download_images(self) -> list[Path]:
        """下载微博图片，返回文件路径列表"""
        headers = {"referer": self.get_referer()}

        async def download_single_image(i: int, img_url: str) -> Path | None:
            """下载单个图片"""
            try:
                if not self.description or self.description == "desktop":
                    content_part = clean_filename(self.content[:20])
                    nickname_part = clean_filename(self.nickname)
                    filename = f"{content_part}_{nickname_part}_{self.id}_{i}.jpg"
                elif self.description == "mapp":
                    ts = int(time())
                    content_part = clean_filename(self.content[:20])
                    desc_part = clean_filename(self.description)
                    nickname_part = clean_filename(self.nickname)
                    filename = (
                        f"{content_part}_{desc_part}_{nickname_part}_{ts}_{i}.jpg"
                    )
                dirname = self.group_id
                if not dirname:
                    filepath = weibo_img_dir / filename
                else:
                    dirpath = weibo_img_dir / dirname
                    dirpath.mkdir(parents=True, exist_ok=True)
                    filepath = dirpath / filename
                result_path = await save_img_by_path(
                    img_url, filepath, True, headers=headers
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

        # 处理转发的图片
        if self.repost and self.repost.images:
            repost_images = await self.repost.download_images()
            saved_images.extend(repost_images)

        return saved_images

    async def download_videos(self) -> list[Path]:
        """下载微博视频，返回文件路径列表"""
        headers = {"referer": self.get_referer()}

        async def download_single_video(i: int, video_url: str) -> Path | None:
            """下载单个视频"""
            try:
                if not self.description or self.description == "desktop":
                    content_part = clean_filename(self.content[:12])
                    nickname_part = clean_filename(self.nickname)
                    filename = f"{content_part}_{nickname_part}_{self.id}_{i}.mp4"
                elif self.description == "mapp":
                    ts = int(time())
                    content_part = clean_filename(self.content[:12])
                    desc_part = clean_filename(self.description)
                    nickname_part = clean_filename(self.nickname)
                    filename = (
                        f"{content_part}_{desc_part}_{nickname_part}_{ts}_{i}.mp4"
                    )
                filepath = weibo_video_dir / filename
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
        self, with_screenshot: bool = True
    ) -> list[Message | MessageSegment]:
        """获取消息列表, 包含截图, 第一个是总览，剩下的是图片或者视频"""
        msg = []
        immsg = []
        ms = None
        cts = []
        if self.nickname:
            msg.append(self.nickname + " 微博~")
        if self.content:
            cts.append(self.content)

        # 下载图片和视频，获取本地路径
        image_paths = await self.download_images()
        video_paths = await self.download_videos()

        # 处理转推
        if self.repost:
            cts.append("------------")
            cts.append("转发自 " + self.repost.nickname)
            cts.append(self.repost.content)
            cts.append("------------")

        # 添加本地图片路径到消息
        for image_path in image_paths:
            immsg.append(MessageSegment.image(image_path))

        # 准备截图任务
        screenshot_task = None
        if with_screenshot:
            if not self.description:
                screenshot_task = get_weibo_screenshot_mobile(self.url)
            elif self.description == "mapp":
                screenshot_task = get_mapp_weibo_screenshot(self.url)
            elif self.description == "desktop":
                screenshot_task = get_weibo_screenshot_desktop(self.url)

        if screenshot_task:
            try:
                ms = await screenshot_task
                if ms:
                    msg.append(str(ms))
            except Exception as e:
                sv.logger.error(f"Error fetching screenshot: {e}")

        if not ms:
            msg.append("\n".join(cts))

        if self.repost and self.repost.url:
            msg.append("源微博详情: " + self.repost.url)
        if self.url:
            msg.append("微博详情: " + self.url)

        res = [Message("\n".join(msg))]
        if immsg:
            num = 4
            for i in (7, 6, 5, 4, 3):
                if len(immsg) % i == 0:
                    num = i
                    break
            for i in range(0, len(immsg), num):
                group = immsg[i : i + num]
                res.append(Message(group))

        # 添加本地视频路径到消息
        for video_path in video_paths:
            res.append(MessageSegment.video(video_path))

        return res

# _cookies_lock = asyncio.Lock()
# _cookies_cache = None


# def _cookie_signature(ck: dict | None) -> str:
#     if not ck:
#         return ""
#     if sub := ck.get("SUB"):
#         return f"SUB:{sub}"
#     if subp := ck.get("SUBP"):
#         return f"SUBP:{subp}"
#     return "|".join(f"{k}={v}" for k, v in sorted(ck.items()))
_cookies_lock = asyncio.Lock()
@on_startup
async def initialize_weibo_cookies():
    ck = await get_weibo_cookies_from_local()
    await save_cookies("weibo", ck)


async def get_weibocookies():
    ck = await get_cookies("weibo")
    return ck

# async def refresh_weibo_visitor_cookies(stale_ck: dict | None = None) -> dict | None:
#     global _cookies_cache
#     stale_sig = _cookie_signature(stale_ck)

#     current = await get_cookies("weibo")
#     if current:
#         current_sig = _cookie_signature(current)
#         if stale_sig and current_sig and current_sig != stale_sig:
#             _cookies_cache = current
#             return current

#     async with _cookies_lock:
#         current = await get_cookies("weibo")
#         if current:
#             current_sig = _cookie_signature(current)
#             if stale_sig and current_sig and current_sig != stale_sig:
#                 _cookies_cache = current
#                 return current

#         ck = await get_weibo_visitor_cookies()
#         if not ck:
#             return None
#         await save_cookies("weibo", ck)
#         _cookies_cache = ck
#         return ck


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
    # ck = cookies
    # attempts = 1
    # last_res = None
    # for attempt in range(attempts):
    res = await aiohttpx.get(
            url,
            headers=headers,
            params=params,
            cookies=cookies if cookies else None,
            follow_redirects=follow_redirects,
            timeout=timeout,
        )
    return res
    #     last_res = res
    #     if not retry_on_ok_minus100 or not res.ok:
    #         return res
    #     try:
    #         ok = res.json.get("ok", 0)
    #     except Exception:
    #         return res
    # return last_res

class _LoginWeiboModule:
    async def get_weibo_list(
        self, target: str, ts: float = 0.0, keywords: list[str] = list()
    ) -> list[WeiboPost]:
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
        if not ck:
            sv.logger.error("error get_weibos_by_mymblog : 获取微博cookies失败")
            return []
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
            sv.logger.error(
                f"获取微博失败: {res.status_code} {res.headers} \n {res.text}, target: {target}"
            )
            return []
        res_data = res.json
        if not res_data["ok"]:
            sv.logger.error(
                f"获取微博失败: {res_data['ok']} {res_data['msg']}, target: {target}"
            )
            return []

        def custom_filter(d) -> bool:
            visible = d.get("visible", {})
            if visible.get("type") not in [0, 6, 7, 8, 9]:
                return False
            user = d.get("user", {})
            if not user or user.get("idstr") != target:
                return False
            text = d["text"]
            parsed_text = _get_text(text)
            kb = False if keywords else True
            if keywords:
                for keyword in keywords:
                    if keyword in parsed_text:
                        kb = True
            created = d["created_at"]
            if created:
                t = datetime.strptime(created, "%a %b %d %H:%M:%S %z %Y").timestamp()
                b = t > ts
            return b and kb

        datalist = res_data.get("data", {}).get("list", [])
        if not datalist:
            sv.logger.error(f"获取微博失败: 没有数据, target: {target}")
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
        url = (
            f"https://weibo.com/ajax/statuses/show?id={bid}&locale=zh-CN&isGetLongText=true"
        )
        try:
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
        except Exception as e:
            sv.logger.error(f"获取微博失败: {e}")
            return None
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
                f"获取微博失败: visible type {type_} not supported, json: {rj}", color=False
            )
            return None
        description = "" if type_ == 0 else "desktop"
        bid = rj.get("mblogid")
        uid = user.get("idstr")
        nickname = user.get("screen_name")
        ts = rj["created_at"]
        created_at = datetime.strptime(ts, "%a %b %d %H:%M:%S %z %Y")
        detail_url = f"https://weibo.com/{uid}/{bid}"
        parsed_text = _get_text(rj["text"])
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
        return WeiboPost(
            uid=uid,
            id=bid,
            timestamp=created_at.timestamp(),
            content=parsed_text,
            url=detail_url,
            images=pic_urls,
            nickname=nickname,
            videos=video_urls,
            description=description,
        )


class _VisitorWeiboModule:
    async def get_weibo_list(
        self, target: str, ts: float = 0.0, keywords: list[str] = list()
    ) -> list[WeiboPost]:
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
        try:
            res_data = res.json
            ok = res_data.get("ok", 0)
        except Exception as e:
            sv.logger.error(
                f"获取微博失败: 解析JSON失败 {e}, ok:{ok}, code:{res.status_code} target: {target}, url: {res.url}, text: {res.text}"
            )
            return []

        if not res_data:
            return []

        if not res_data["ok"] and res_data["msg"] != "这里还没有内容":
            return []

        def custom_filter(d) -> bool:
            if d.get("mblog") is None:
                return False
            text = d["mblog"]["text"]
            kb = False if keywords else True
            if keywords:
                for keyword in keywords:
                    if keyword in text:
                        kb = True
            created = d["mblog"]["created_at"]
            if created:
                t = datetime.strptime(created, "%a %b %d %H:%M:%S %z %Y").timestamp()
                b = t > ts
            return d["card_type"] in [9, 6, 7] and b and kb

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
            sv.logger.error(f"{res.url} 获取微博失败: {res.status_code} {res.text}")
            return None
        rj: dict = res.json
        if not rj.get("ok", False):
            sv.logger.error(f"{res.url} 获取微博失败: {res.status_code} {res.text}")
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
        parsed_text = _get_text(info["text"])
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
            video_urls = [img["videoSrc"] for img in raw_pics_list if img.get("videoSrc")]
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
        return WeiboPost(
            uid=info["user"]["id"],
            id=info["bid"],
            timestamp=created_at.timestamp(),
            content=parsed_text,
            url=detail_url,
            images=pic_urls,
            nickname=info["user"]["screen_name"],
            videos=video_urls,
        )


_login_weibo_module = _LoginWeiboModule()
_visitor_weibo_module = _VisitorWeiboModule()


async def get_weibo_list(
    target: str, ts: float = 0.0, keywords: list[str] = list()
) -> list[WeiboPost]:
    ck = await get_weibocookies()
    if not ck:
        return []
    if ck.get("MLOGIN"):
        return await _visitor_weibo_module.get_weibo_list(target, ts, keywords)
    return await _login_weibo_module.get_weibo_list(target, ts, keywords)


async def get_weibo_new(
    target: str, ts: float = 0.0, keywords: list[str] = list()
) -> WeiboPost | None:
    ls = await get_weibo_list(target, ts, keywords)
    return ls[0] if ls else None

async def parse_weibo_with_id(id: str) -> WeiboPost | None:
    ck = await get_weibocookies()
    if ck:
        if not ck.get("MLOGIN"):
            return await _login_weibo_module.parse_weibo(id)
    return await _visitor_weibo_module.parse_weibo(id)


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


class Base(DeclarativeBase):
    pass


class WeiboDB(Base):
    __tablename__ = "weibodb"
    uid: Mapped[str] = mapped_column(Text, primary_key=True)
    group: Mapped[int] = mapped_column(Integer, primary_key=True)
    time: Mapped[float] = mapped_column(Float, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    keyword: Mapped[str] = mapped_column(Text, default="", nullable=False)


# 初始化数据库
if not os.path.exists(db_path):
    Base.metadata.create_all(engine)


# 解析微博文本，处理HTML标签
def _get_text(raw_text: str) -> str:
    text = raw_text.replace("<br/>", "\n").replace("<br />", "\n")
    soup = BeautifulSoup(text, "lxml")

    if not soup:
        return text

    for br in soup.find_all("br"):
        br.replace_with("\n")

    for a in soup.find_all("a", href=True):
        span = a.find("span", class_="surl-text")
        if span:
            text = span.get_text()
            url = a["href"]
            if (
                not text.startswith("#")
                and not text.endswith("#")
                and (
                    url.startswith("https://weibo.cn/sinaurl?u=")
                    or url.startswith("https://video.weibo.com")
                )
            ):
                url = unquote(url.replace("https://weibo.cn/sinaurl?u=", ""))
                span.string = f"{text}( {url} )"

    return soup.get_text()

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
    if vd := pic.get("video"):
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
