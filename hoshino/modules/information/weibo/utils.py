import asyncio
from dataclasses import dataclass
from datetime import datetime
import functools
import os
import re
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
from hoshino.util.playwrights import (
    get_mapp_weibo_screenshot,
    get_weibo_screenshot_mobile,
    get_weibo_screenshot_desktop,
)

from ..utils import Post
from nonebot.typing import override

sv = Service("weibo", enable_on_default=False, visible=False)


def clean_filename(text: str) -> str:
    """清理文件名，替换空格、换行符和其他问题字符为短横线"""
    if not text:
        return "unnamed"

    # 替换空格、换行符、制表符等空白字符为短横线
    cleaned = re.sub(r"\s+", "-", text.strip())

    # 移除或替换文件系统不支持的字符
    # Windows/Linux 文件名不能包含: \ / : * ? " < > |
    cleaned = re.sub(r'[\\/:*?"<>|\r\n\t]', "-", cleaned)

    # 移除连续的短横线
    cleaned = re.sub(r"-+", "-", cleaned)

    # 移除开头和结尾的短横线
    cleaned = cleaned.strip("-")

    # 如果清理后为空，返回默认名称
    return cleaned if cleaned else "unnamed"


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

    @override
    def get_referer(self) -> str:
        """获取微博的referer"""
        return "https://weibo.com"

    async def download_images(self) -> list[str]:
        """下载微博图片"""
        if not self.images:
            return []
        headers = {"referer": self.get_referer()}
        saved_images = []
        for i, img_url in enumerate(self.images):
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
                filepath = weibo_img_dir / filename
                result_path = await save_img_by_path(
                    img_url, filepath, True, headers=headers
                )
                if result_path:
                    saved_images.append(result_path.name)
                else:
                    sv.logger.error(f"Failed to save image {img_url}")
            except Exception as e:
                sv.logger.error(f"Error downloading image {img_url}: {e}")
        if self.repost and self.repost.images:
            saved_images.extend(await self.repost.download_images())
        return saved_images

    async def download_videos(self) -> list[str]:
        """下载微博视频"""
        if not self.videos:
            return []
        headers = {"referer": self.get_referer()}
        saved_videos = []
        for i, video_url in enumerate(self.videos):
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
                    saved_videos.append(result_path.name)
                else:
                    sv.logger.error(f"Failed to save video {video_url}")
            except Exception as e:
                sv.logger.error(f"Error downloading video {video_url}: {e}")
        if self.repost and self.repost.videos:
            saved_videos.extend(await self.repost.download_videos())
        return saved_videos

    @override
    async def get_message(
        self, with_screenshot: bool = True
    ) -> list[Message | MessageSegment]:
        """获取消息列表, 包含截图, 第一个是总览，剩下的是图片或者视频"""
        msg = []
        immsg = []
        ms = None
        videos = self.videos
        cts = []
        if self.nickname:
            msg.append(self.nickname + "微博~")
        if self.content:
            cts.append(self.content)
        # 处理转推
        if self.repost:
            cts.append("------------")
            cts.append("转发自 " + self.repost.nickname)
            cts.append(self.repost.content)
            cts.append("------------")
            if self.repost.images:
                for img in self.repost.images:
                    immsg.append(MessageSegment.image(img))
            if self.repost.videos:
                videos.extend(self.repost.videos)
        tasks = []
        # Prepare image fetch tasks
        if self.images:
            for image_url in self.images:
                headers = {"referer": self.get_referer()}
                tasks.append(aiohttpx.get(image_url, headers=headers))
        # Prepare screenshot task
        screenshot_task = None
        if with_screenshot:
            if not self.description:
                screenshot_task = get_weibo_screenshot_mobile(self.url)
                tasks.append(screenshot_task)
            elif self.description == "mapp":
                screenshot_task = get_mapp_weibo_screenshot(self.url)
                tasks.append(screenshot_task)
            elif self.description == "desktop":
                screenshot_task = get_weibo_screenshot_desktop(self.url)
                tasks.append(screenshot_task)
        responses = await asyncio.gather(*tasks, return_exceptions=True)
        image_count = len(self.images) if self.images else 0
        for i in range(image_count):
            resp = responses[i]
            if isinstance(resp, Exception):
                sv.logger.error(f"Error fetching image: {resp}")
                immsg.append(MessageSegment.image(self.images[i]))
            elif resp.ok:
                immsg.append(MessageSegment.image(resp.content))
            else:
                immsg.append(MessageSegment.image(self.images[i]))

        if screenshot_task:
            if isinstance(responses[-1], Exception):
                sv.logger.error(f"Error fetching screenshot: {responses[-1]}")
            elif isinstance(responses[-1], MessageSegment):
                ms = responses[-1]

            if ms:
                msg.append(str(ms))
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
        if videos:
            # no download , or it may cause oom
            for video in videos:
                res.append(MessageSegment.video(video))
        return res


get_weibocookies = functools.partial(get_cookies, "weibo")


async def get_sub_list(
    target: str, ts: float = 0.0, keywords: list[str] = list()
) -> list[WeiboPost]:
    ck = await get_weibocookies()
    if not ck:
        return await get_weibos_by_containerid(target, ts, keywords)
    return await get_weibos_by_mymblog(target, ts, keywords)


async def get_sub_new(
    target: str, ts: float = 0.0, keywords: list[str] = list()
) -> WeiboPost | None:
    ls = await get_sub_list(target, ts, keywords)
    return ls[0] if ls else None


async def get_weibos_by_mymblog(
    target: str, ts: float = 0.0, keywords: list[str] = list()
) -> list[WeiboPost]:
    header = {
        "Referer": f"https://weibo.com/u/{target}",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/ 91.0.4472.124 Safari/537.36",
        "accept": "application/json",
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
    res = await aiohttpx.get(
        "https://weibo.com/ajax/statuses/mymblog",
        headers=header,
        params=params,
        cookies=ck,
        timeout=6.0,
    )
    if not res.ok:
        sv.logger.error(f"获取微博失败: {res.status_code}")
        return []
    res_data = res.json
    if not res_data["ok"]:
        sv.logger.error(f"获取微博失败: {res_data['ok']} {res_data['msg']}")
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
        post = parse_weibo_with_bid_dict(i)
        if not post:
            continue
        postlist.append(post)
    postlist.sort(key=lambda x: x.timestamp, reverse=True)
    return postlist


async def get_weibos_by_containerid(
    target: str, ts: float = 0.0, keywords: list[str] = list()
) -> list[WeiboPost]:
    header = {
        "Referer": f"https://m.weibo.cn/u/{target}",
        "MWeibo-Pwa": "1",
        "X-Requested-With": "XMLHttpRequest",
    }
    params = {"containerid": "107603" + target}
    ck = await get_weibocookies()
    res = await aiohttpx.get(
        "https://m.weibo.cn/api/container/getIndex?",
        headers=header,
        params=params,
        cookies=ck if ck else None,
        timeout=6.0,
    )
    res_data = res.json
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
    ls = list(filter(custom_filter, res_data["data"]["cards"]))
    ls.sort(key=k, reverse=True)
    if not ls:
        return []
    res = []
    for i in ls:
        post = parse_weibo_card_raw(i)
        if not post:
            continue
        if post.timestamp > ts:
            res.append(post)
    return res


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


async def parse_weibo_with_bid(bid: str) -> WeiboPost | None:
    url = (
        f"https://weibo.com/ajax/statuses/show?id={bid}&locale=zh-CN&isGetLongText=true"
    )
    try:
        res = await aiohttpx.get(
            url,
            cookies=await get_weibocookies(),
            timeout=5.0,
        )
        rj = res.json
    except Exception as e:
        sv.logger.error(f"获取微博失败: {e}")
        return None
    return parse_weibo_with_bid_dict(rj)


def parse_mix_media_info(dic: dict) -> tuple[list[str], list[str]]:
    pic_urls = []
    video_urls = []
    medias = dic.get("mix_media_info", {}).get("items", [])
    for media in medias:
        mediadata = media.get("data", {})
        if media.get("type") == "pic":
            pic_url = parse_pic_info(mediadata)
            if pic_url:
                pic_urls.append(pic_url)
        elif media.get("type") == "video":
            v_url, p_url = parse_video_info(mediadata)
            if v_url:
                video_urls.append(v_url)
            if p_url:
                pic_urls.append(p_url)
    return pic_urls, video_urls


def parse_pic_info(pic: dict) -> str:
    pic_url = ""
    for scale in ["original", "large"]:
        if scale in pic:
            if ur := pic[scale].get("url"):
                pic_url = ur
                break
    return pic_url


def parse_video_info(page_info: dict) -> str:
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


def parse_weibo_with_bid_dict(rj: dict) -> WeiboPost | None:
    post = _parse_weibo_with_bid_dict(rj)
    if not post:
        return None
    if "retweeted_status" in rj:
        if rj["retweeted_status"].get("visible", {}).get("type") == 10:
            return post
        repost = _parse_weibo_with_bid_dict(rj["retweeted_status"])
        if repost:
            post.repost = repost
    return post


def _parse_weibo_with_bid_dict(rj: dict) -> WeiboPost | None:
    if rj.get("user") is None:
        sv.logger.error("获取微博失败: User is None")
        return None
    visible = rj.get("visible", {})
    type_ = visible.get("type", 0)
    if type_ not in [0, 6, 7, 8, 9]:
        sv.logger.error(f"获取微博失败: visible type {type_} not supported")
        return None
    description = "" if type_ == 0 else "desktop"
    mid = rj.get("mid")
    bid = rj.get("mblogid")
    uid = rj.get("user", {}).get("idstr")
    nickname = rj.get("user", {}).get("screen_name")
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
            pic_url = parse_pic_info(pic)
            if pic_url:
                pic_urls.append(pic_url)
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


def _parse_weibo_card(info: dict) -> WeiboPost | None:
    parsed_text = _get_text(info["text"])
    pic_num = info.get("pic_num", 0)
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


def parse_weibo_card_raw(raw: dict) -> WeiboPost | None:
    info = raw["mblog"]
    return parse_weibo_card(info)


def parse_weibo_card(info: dict) -> WeiboPost | None:
    post = _parse_weibo_card(info)
    if not post:
        return None
    if "retweeted_status" in info:
        if info["retweeted_status"].get("visible", {}).get("type") != 0:
            return post
        post.repost = _parse_weibo_card(info["retweeted_status"])
    return post


async def parse_weibo_with_id(id: str) -> WeiboPost | None:
    ck = await get_weibocookies()
    if ck:
        return await parse_weibo_with_bid(id)
    url = "https://m.weibo.cn/statuses/show?id={}".format(id)
    ck = "_T_WM=40835919903; WEIBOCN_FROM=1110006030; MLOGIN=0; XSRF-TOKEN=4399c8"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/ 91.0.4472.124 Safari/537.36",
        "Cookie": ck,
        "Referer": "https://m.weibo.cn/detail/{}".format(id),
        "accept": "application/json",
    }
    res = await aiohttpx.get(
        url,
        headers=headers,
        timeout=8.0,
    )
    if not res.ok:
        sv.logger.error(f"获取微博失败: {res.status_code} {res.text}")
        return None
    rj = res.json
    if not rj.get("ok", False):
        sv.logger.error(f"获取微博失败: {res.status_code} {res.text}")
        return None
    rjdata = rj.get("data", {})
    return parse_weibo_card(rjdata)


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
    resp = await aiohttpx.get(
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
