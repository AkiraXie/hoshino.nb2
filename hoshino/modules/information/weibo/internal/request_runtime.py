import asyncio
import functools
import re
from datetime import datetime
from time import time

from bs4 import BeautifulSoup

from hoshino.util import (
    aiohttpx,
    get_cookies,
    get_redirect,
    send_to_superuser,
)

from ..post import WeiboPost
from ..sv import sv


_WEIBO_TIME_FORMAT = "%a %b %d %H:%M:%S %z %Y"
_VISIBLE_TYPES_LOGIN = {0, 6, 7, 8, 9}


def _parse_weibo_timestamp(ts_str: str) -> float:
    return datetime.strptime(ts_str, _WEIBO_TIME_FORMAT).timestamp()


def filter_page_info(page_info: dict) -> bool:
    if not page_info:
        return True
    obj_type = page_info.get("object_type")
    if obj_type in {"event", "article", "hudongvote", "wb_collection"}:
        return False
    typ = page_info.get("type")
    typ = str(typ).lower() if typ else ""
    if typ in {"24", "23", "2"}:
        return False
    if page_info.get("buttons") is not None:
        return False
    return True


def parse_mix_media_info(raw: dict) -> tuple[list[str], list[str]]:
    pic_urls: list[str] = []
    video_urls: list[str] = []
    for media in raw.get("mix_media_info", {}).get("items", []):
        media_data = media.get("data", {})
        if media.get("type") == "pic":
            pic_url, video_url = parse_pic_info(media_data)
            if pic_url:
                pic_urls.append(pic_url)
            if video_url:
                video_urls.append(video_url)
        elif media.get("type") == "video":
            video_url, pic_url = parse_video_info(media_data)
            if video_url:
                video_urls.append(video_url)
            if pic_url:
                pic_urls.append(pic_url)
    return pic_urls, video_urls


def parse_pic_info(pic: dict) -> tuple[str, str]:
    pic_url = ""
    video_url = ""
    if pic.get("type") == "livephoto" and pic.get("video"):
        video_url = pic["video"]
    for scale in ["largest", "original", "large"]:
        if scale in pic and (url := pic[scale].get("url")):
            pic_url = url
            break
    return pic_url, video_url


def parse_video_info(page_info: dict) -> tuple[str, str]:
    pic_url = ""
    video_url = ""
    media_info = page_info.get("media_info", {})
    page_urls = page_info.get("urls", {})
    big_pic = media_info.get("big_pic_info", {}).get("pic_big", {}).get("url", "")
    if big_pic:
        pic_url = big_pic
    else:
        page_pic = page_info.get("page_pic", "")
        pic_url = page_pic.get("url", "") if isinstance(page_pic, dict) else page_pic

    for key in [
        "mp4_720p_mp4",
        "mp4_hd_url",
        "mp4_sd_url",
        "stream_url_hd",
        "stream_url",
        "mp4_hd_mp4",
        "mp4_ld_mp4",
        "mp4_sd_mp4",
    ]:
        if key in media_info:
            video_url = media_info[key]
            break
        if key in page_urls:
            video_url = page_urls[key]
            break
    return video_url, pic_url


class WeiboRequestError(Exception):
    def __init__(self, message: str, *, reason: str = "", target: str = ""):
        super().__init__(message)
        self.reason = reason
        self.target = target


class _WeiboHttpSession:
    async def get_cookies(self) -> dict:
        return await get_cookies("weibo")

    async def get(
        self,
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
            response = await aiohttpx.get(
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

        self._check_response(
            response,
            params=params,
            retry_on_ok_minus100=retry_on_ok_minus100,
        )
        return response

    def _check_response(
        self,
        response: aiohttpx.Response,
        *,
        params: dict | None,
        retry_on_ok_minus100: bool,
    ) -> None:
        url = str(response.url)
        target = self._extract_target(url, params)
        target_info = f", target: {target}" if target else ""

        if not response.ok:
            raise WeiboRequestError(
                f"微博请求失败: status={response.status_code}, url: {url}{target_info}, text: {response.text}",
                reason="http_error",
                target=target,
            )

        try:
            res_data = response.json
        except Exception:
            return

        if not isinstance(res_data, dict):
            return

        ok = res_data.get("ok")
        msg = str(res_data.get("msg", ""))
        data = res_data.get("data", {})

        if ok is None:
            raise WeiboRequestError(
                f"微博请求失败: 该账号已被封禁或风控, url: {url}{target_info}, text: {response.text}",
                reason="account_banned",
                target=target,
            )
        if ok == -100 and retry_on_ok_minus100:
            raise WeiboRequestError(
                f"微博请求失败: cookies 可能失效(ok=-100), url: {url}{target_info}, msg: {msg}",
                reason="cookie_invalid",
                target=target,
            )
        if "用户不存在" in msg:
            raise WeiboRequestError(
                f"微博请求失败: 用户不存在, url: {url}{target_info}, msg: {msg}",
                reason="user_not_found",
                target=target,
            )
        if isinstance(data, dict):
            if "ajax/statuses/mymblog" in url and not data.get("list", []):
                raise WeiboRequestError(
                    f"微博请求失败: 账号暂无数据, url: {url}{target_info}",
                    reason="no_data",
                    target=target,
                )
            if "api/container/getIndex" in url and not data.get("cards", []):
                raise WeiboRequestError(
                    f"微博请求失败: 账号暂无数据, url: {url}{target_info}",
                    reason="no_data",
                    target=target,
                )
        if ok in (0, False) and msg:
            raise WeiboRequestError(
                f"微博请求失败: ok={ok}, url: {url}{target_info}, msg: {msg}",
                reason="api_error",
                target=target,
            )

    def _extract_target(self, url: str, params: dict | None) -> str:
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


class WeiboPostParser:
    def parse_login(self, raw: dict) -> WeiboPost | None:
        user = raw.get("user")
        if not user:
            return None
        visible_type = raw.get("visible", {}).get("type", 0)
        if visible_type not in _VISIBLE_TYPES_LOGIN:
            return None

        post = self._build_post(
            uid=user.get("idstr", ""),
            post_id=raw.get("mblogid", ""),
            nickname=user.get("screen_name", ""),
            created_at=raw.get("created_at", ""),
            content_html=raw.get("text", ""),
            images=self._collect_login_media(raw)[0],
            videos=self._collect_login_media(raw)[1],
            description="" if visible_type == 0 else "desktop",
            avatar_url=user.get("avatar_hd", ""),
        )
        return self._attach_repost(
            post,
            raw,
            repost_key="retweeted_status",
            parse_fn=self.parse_login,
            visible_check=lambda repost_raw: repost_raw.get("visible", {}).get("type") != 10,
        )

    def parse_visitor(self, raw: dict) -> WeiboPost | None:
        info = raw.get("mblog", raw) if isinstance(raw, dict) else {}
        if not info or "user" not in info or "bid" not in info:
            return None

        images, videos = self._collect_visitor_media(info)
        post = self._build_post(
            uid=str(info["user"].get("id", "")),
            post_id=info["bid"],
            nickname=info["user"].get("screen_name", ""),
            created_at=info.get("created_at", ""),
            content_html=info.get("text", ""),
            images=images,
            videos=videos,
        )
        return self._attach_repost(
            post,
            info,
            repost_key="retweeted_status",
            parse_fn=self.parse_visitor,
            visible_check=lambda repost_raw: repost_raw.get("visible", {}).get("type") == 0,
        )

    def _build_post(
        self,
        *,
        uid: str,
        post_id: str,
        nickname: str,
        created_at: str,
        content_html: str,
        images: list[str],
        videos: list[str],
        description: str = "",
        avatar_url: str = "",
    ) -> WeiboPost:
        post = WeiboPost(
            uid=str(uid),
            id=str(post_id),
            content="",
            images=list(images),
            videos=list(videos),
            timestamp=datetime.strptime(created_at, _WEIBO_TIME_FORMAT).timestamp(),
            url=f"https://weibo.com/{uid}/{post_id}",
            nickname=nickname,
            description=description,
            user_avatar_image=avatar_url,
        )
        post._get_text(content_html)
        return post

    def _attach_repost(
        self,
        post: WeiboPost | None,
        raw: dict,
        *,
        repost_key: str,
        parse_fn,
        visible_check,
    ) -> WeiboPost | None:
        if not post:
            return None
        repost_raw = raw.get(repost_key)
        if not repost_raw or not visible_check(repost_raw):
            return post
        repost = parse_fn(repost_raw)
        if repost:
            post.repost = repost
            post.images = [image for image in post.images if image not in repost.images]
            post.videos = [video for video in post.videos if video not in repost.videos]
        return post

    def _collect_login_media(self, raw: dict) -> tuple[list[str], list[str]]:
        if "mix_media_info" in raw:
            return parse_mix_media_info(raw)

        pic_urls: list[str] = []
        video_urls: list[str] = []
        for pic in raw.get("pic_infos", {}).values():
            pic_url, video_url = parse_pic_info(pic)
            if pic_url:
                pic_urls.append(pic_url)
            if video_url:
                video_urls.append(video_url)
        page_info = raw.get("page_info", {})
        if page_info.get("object_type") == "video":
            video_url, pic_url = parse_video_info(page_info)
            if video_url:
                video_urls.append(video_url)
            if pic_url:
                pic_urls.append(pic_url)
        return pic_urls, video_urls

    def _collect_visitor_media(self, info: dict) -> tuple[list[str], list[str]]:
        pic_urls: list[str] = []
        video_urls: list[str] = []
        raw_pics = info.get("pics", [])
        if isinstance(raw_pics, dict):
            for image in raw_pics.values():
                if image.get("large"):
                    pic_urls.append(image["large"]["url"])
                if image.get("videoSrc"):
                    video_urls.append(image["videoSrc"])
        elif isinstance(raw_pics, list):
            pic_urls.extend(
                image["large"]["url"]
                for image in raw_pics
                if image.get("large")
            )
            video_urls.extend(
                image["videoSrc"]
                for image in raw_pics
                if image.get("videoSrc")
            )
        page_info = info.get("page_info", {})
        if page_info.get("type") == "video":
            video_url, pic_url = parse_video_info(page_info)
            if video_url:
                video_urls.append(video_url)
            if pic_url:
                pic_urls.append(pic_url)
        return pic_urls, video_urls


class _BaseWeiboSource:
    def __init__(self, session: _WeiboHttpSession, parser: WeiboPostParser) -> None:
        self.session = session
        self.parser = parser

    async def fetch_list(self, target: str, ts: float, cookies: dict) -> list[WeiboPost]:
        response = await self.session.get(
            self.list_url,
            headers=self.build_list_headers(target, cookies),
            params=self.build_list_params(target),
            cookies=cookies,
            follow_redirects=self.list_follow_redirects,
            timeout=self.list_timeout,
        )
        items = self.extract_list_items(response.json)
        filtered = [item for item in items if self.should_include(item, target, ts)]
        filtered.sort(key=functools.cmp_to_key(self.compare_items), reverse=True)
        posts = [self.parse_item(item) for item in filtered]
        return [post for post in posts if post and post.timestamp > ts]

    async def fetch_detail(self, post_id: str, cookies: dict | None) -> WeiboPost | None:
        response = await self.session.get(
            self.build_detail_url(post_id),
            headers=self.build_detail_headers(post_id),
            cookies=cookies,
            follow_redirects=self.detail_follow_redirects,
            timeout=self.detail_timeout,
        )
        raw = self.extract_detail_item(response.json)
        return self.parse_item(raw)

    @property
    def list_url(self) -> str:
        raise NotImplementedError

    @property
    def list_timeout(self) -> float:
        return 6.0

    @property
    def detail_timeout(self) -> float:
        return 8.0

    @property
    def list_follow_redirects(self) -> bool:
        return True

    @property
    def detail_follow_redirects(self) -> bool:
        return True

    def build_list_headers(self, target: str, cookies: dict) -> dict:
        raise NotImplementedError

    def build_list_params(self, target: str) -> dict:
        raise NotImplementedError

    def build_detail_headers(self, post_id: str) -> dict:
        raise NotImplementedError

    def build_detail_url(self, post_id: str) -> str:
        raise NotImplementedError

    def extract_list_items(self, payload: dict) -> list[dict]:
        raise NotImplementedError

    def extract_detail_item(self, payload: dict) -> dict:
        raise NotImplementedError

    def should_include(self, raw: dict, target: str, ts: float) -> bool:
        raise NotImplementedError

    def compare_items(self, left: dict, right: dict) -> float:
        raise NotImplementedError

    def parse_item(self, raw: dict) -> WeiboPost | None:
        raise NotImplementedError


class _LoginSource(_BaseWeiboSource):
    @property
    def list_url(self) -> str:
        return "https://weibo.com/ajax/statuses/mymblog"

    @property
    def detail_timeout(self) -> float:
        return 5.0

    def build_list_headers(self, target: str, cookies: dict) -> dict:
        return {
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
            "X-Xsrf-Token": cookies.get("XSRF-TOKEN", ""),
        }

    def build_list_params(self, target: str) -> dict:
        return {"uid": target, "page": 1, "feature": 0}

    def build_detail_headers(self, post_id: str) -> dict:
        return {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
            "Referer": "https://weibo.com/",
        }

    def build_detail_url(self, post_id: str) -> str:
        return f"https://weibo.com/ajax/statuses/show?id={post_id}&locale=zh-CN&isGetLongText=true"

    def extract_list_items(self, payload: dict) -> list[dict]:
        return payload.get("data", {}).get("list", [])

    def extract_detail_item(self, payload: dict) -> dict:
        return payload

    def should_include(self, raw: dict, target: str, ts: float) -> bool:
        if not filter_page_info(raw.get("page_info", {})):
            return False
        if raw.get("visible", {}).get("type") not in _VISIBLE_TYPES_LOGIN:
            return False
        user = raw.get("user", {})
        if not user or user.get("idstr") != target:
            return False
        created = raw.get("created_at")
        return bool(created and _parse_weibo_timestamp(created) > ts)

    def compare_items(self, left: dict, right: dict) -> float:
        return _parse_weibo_timestamp(left["created_at"]) - _parse_weibo_timestamp(right["created_at"])

    def parse_item(self, raw: dict) -> WeiboPost | None:
        return self.parser.parse_login(raw)


class _VisitorSource(_BaseWeiboSource):
    @property
    def list_url(self) -> str:
        return "https://m.weibo.cn/api/container/getIndex?"

    @property
    def list_follow_redirects(self) -> bool:
        return False

    @property
    def detail_follow_redirects(self) -> bool:
        return False

    def build_list_headers(self, target: str, cookies: dict) -> dict:
        return {
            "MWeibo-Pwa": "1",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": f"https://m.weibo.cn/u/{target}",
            "sec-fetch-mode": "cors",
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 11_0 like Mac OS X) AppleWebKit/604.1.38 (KHTML, like Gecko) Version/11.0 Mobile/15A372 Safari/604.1",
        }

    def build_list_params(self, target: str) -> dict:
        return {
            "type": "uid",
            "value": target,
            "containerid": "107603" + target,
        }

    def build_detail_headers(self, post_id: str) -> dict:
        return {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/ 91.0.4472.124 Safari/537.36",
            "Origin": "https://m.weibo.cn",
            "Referer": f"https://m.weibo.cn/detail/{post_id}",
            "Accept": "application/json, text/plain, */*",
            "x-requested-with": "XMLHttpRequest",
            "mweibo-pwa": "1",
            "sec-fetch-site": "same-origin",
            "sec-fetch-mode": "cors",
            "sec-fetch-dest": "empty",
        }

    def build_detail_url(self, post_id: str) -> str:
        return f"https://m.weibo.cn/statuses/show?id={post_id}&_={int(time() * 1000)}"

    def extract_list_items(self, payload: dict) -> list[dict]:
        return payload.get("data", {}).get("cards", [])

    def extract_detail_item(self, payload: dict) -> dict:
        if not payload.get("ok", False):
            return {}
        return {"mblog": payload.get("data", {})}

    def should_include(self, raw: dict, target: str, ts: float) -> bool:
        mblog = raw.get("mblog")
        if not mblog:
            return False
        created = mblog.get("created_at")
        if not created:
            return False
        return raw.get("card_type") in [9, 6, 7] and _parse_weibo_timestamp(created) > ts

    def compare_items(self, left: dict, right: dict) -> float:
        return _parse_weibo_timestamp(left["mblog"]["created_at"]) - _parse_weibo_timestamp(right["mblog"]["created_at"])

    def parse_item(self, raw: dict) -> WeiboPost | None:
        return self.parser.parse_visitor(raw)


class _MappWeiboParser:
    def __init__(self, session: _WeiboHttpSession) -> None:
        self.session = session

    async def parse(self, url: str, detail_loader) -> WeiboPost | None:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 NetType/WIFI MicroMessenger/7.0.20.1781(0x6700143B) WindowsWechat(0x63090a13) UnifiedPCWindowsWechat(0xf254032b) XWEB/13655 Flue",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Authority": "mapp.api.weibo.cn",
        }
        if redirect_url := await get_redirect(url, headers=headers):
            matched = re.search(r"m.weibo.cn\/(detail|status)\/(\w+)", redirect_url)
            if matched:
                return await detail_loader(matched.group(2))

        response = await self.session.get(url, headers=headers, timeout=8.0)
        if not response.text:
            return None

        soup = BeautifulSoup(response.text, "lxml")
        img_urls = []
        for image in soup.find_all("img", class_="f-bg-imgs"):
            if image.get("bak_src"):
                img_urls.append(image["data-src"])
            elif image.get("src"):
                img_urls.append(image["src"])

        parsed_text = ""
        for div in soup.find_all("div", class_="weibo-text"):
            parsed_text += div.get_text(strip=True).replace("&ZeroWidthSpace;", "") + "\n"

        video_urls = []
        for video in soup.find_all("video", id="video"):
            if video.get("src"):
                video_urls.append(video["src"])
            if video.get("poster"):
                img_urls.append(video["poster"])

        nickname = ""
        m_text_box = soup.find("div", class_="m-text-box")
        if m_text_box and (nickname_span := m_text_box.find("span")):
            nickname = nickname_span.get_text(strip=True)

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


class WeiboRequestRuntime:
    def __init__(self) -> None:
        self.session = _WeiboHttpSession()
        self.parser = WeiboPostParser()
        self.login_source = _LoginSource(self.session, self.parser)
        self.visitor_source = _VisitorSource(self.session, self.parser)
        self.mapp_parser = _MappWeiboParser(self.session)
        self._missing_target_queue: asyncio.Queue[str] = asyncio.Queue()
        self._missing_target_set: set[str] = set()

    async def get_weibocookies(self) -> dict:
        return await self.session.get_cookies()

    async def get_weibo_list(self, target: str, ts: float = 0.0) -> list[WeiboPost]:
        cookies = await self.get_weibocookies()
        if not cookies:
            return []
        try:
            source = self._select_list_source(cookies)
            return await source.fetch_list(target, ts, cookies)
        except WeiboRequestError as e:
            if e.reason in {"user_not_found", "account_banned"}:
                await self.enqueue_missing_target(target)
            return []

    async def get_weibo_new(self, target: str, ts: float = 0.0) -> WeiboPost | None:
        posts = await self.get_weibo_list(target, ts)
        return posts[0] if posts else None

    async def parse_weibo_with_id(self, post_id: str) -> WeiboPost | None:
        cookies = await self.get_weibocookies()
        try:
            source = self._select_detail_source(cookies)
            return await source.fetch_detail(post_id, cookies)
        except WeiboRequestError as e:
            if e.reason in {"user_not_found", "account_banned"}:
                await self.enqueue_missing_target(e.target)
            return None

    async def parse_mapp_weibo(self, url: str) -> WeiboPost | None:
        return await self.mapp_parser.parse(url, self.parse_weibo_with_id)

    async def enqueue_missing_target(self, target: str) -> bool:
        if not target or target in self._missing_target_set:
            return False
        self._missing_target_set.add(target)
        await self._missing_target_queue.put(target)
        return True

    async def missing_target_worker(self) -> None:
        while True:
            try:
                target = self._missing_target_queue.get_nowait()
            except asyncio.QueueEmpty:
                await asyncio.sleep(3)
                continue
            try:
                await self.process_missing_target(target)
            except Exception as e:
                sv.logger.error(f"处理微博不存在账号队列失败: target={target}, error: {e}")
            finally:
                self._missing_target_set.discard(target)
                self._missing_target_queue.task_done()

    async def process_missing_target(self, target: str) -> None:
        from ..db import remove_subscriptions_by_uid, uid_has_any_subscription
        from ..sub import uid_manager

        confirmed = await self._confirm_missing_target(target)
        if not confirmed:
            sv.logger.info(f"微博账号不存在待删除任务跳过: target={target}, 二次确认未命中")
            return

        deleted_count = remove_subscriptions_by_uid(target)
        if not deleted_count:
            sv.logger.info(f"微博账号不存在待删除任务跳过: target={target}, 数据库中无订阅")
            return

        await uid_manager.remove_uid(target, lambda uid: uid_has_any_subscription(uid))
        message = f"微博账号不存在，已自动删除订阅: UID {target}, 共 {deleted_count} 条"
        sv.logger.warning(message)
        await send_to_superuser(message)

    async def _confirm_missing_target(self, target: str) -> bool:
        cookies = await self.get_weibocookies()
        source = self._select_list_source(cookies)
        try:
            await source.fetch_list(target, 0.0, cookies)
        except WeiboRequestError as e:
            return e.reason in {"user_not_found", "account_banned"}
        return False

    def _select_list_source(self, cookies: dict | None) -> _BaseWeiboSource:
        if cookies and cookies.get("MLOGIN"):
            return self.visitor_source
        return self.login_source

    def _select_detail_source(self, cookies: dict | None) -> _BaseWeiboSource:
        if cookies and not cookies.get("MLOGIN"):
            return self.login_source
        return self.visitor_source


_runtime = WeiboRequestRuntime()


async def get_weibocookies() -> dict:
    return await _runtime.get_weibocookies()


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
    return await _runtime.session.get(
        url,
        headers=headers,
        params=params,
        cookies=cookies,
        follow_redirects=follow_redirects,
        timeout=timeout,
        retry_on_ok_minus100=retry_on_ok_minus100,
    )


async def missing_weibo_target_worker() -> None:
    await _runtime.missing_target_worker()


async def process_missing_weibo_target(target: str) -> None:
    await _runtime.process_missing_target(target)


async def get_weibo_list(target: str, ts: float = 0.0) -> list[WeiboPost]:
    return await _runtime.get_weibo_list(target, ts)


async def get_weibo_new(target: str, ts: float = 0.0) -> WeiboPost | None:
    return await _runtime.get_weibo_new(target, ts)


async def parse_weibo_with_id(post_id: str) -> WeiboPost | None:
    return await _runtime.parse_weibo_with_id(post_id)


async def parse_mapp_weibo(url: str) -> WeiboPost | None:
    return await _runtime.parse_mapp_weibo(url)
