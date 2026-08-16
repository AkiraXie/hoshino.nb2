"""NGA 帖子解析：bbs.nga.cn / nga.178.com / ngabbs.com 的 read.php 链接。

访客访问 NGA 会先被 guestJs JS 挑战拦截（403）。挑战页里带 ``document.cookie =
'guestJs=...'`` 脚本并下发 ngaPassportUid/lastvisit 等 Set-Cookie；带这些 cookie
重试同一 URL（加 rand 参数）即可拿到真实内容。内容走 ``__output=11`` JSON API
（``data.__T`` 标题 / ``data.__U`` 用户 / ``data.__R`` 楼层），比 HTML 版稳定。
"""

from __future__ import annotations

import asyncio
import json
import random
import re
from pathlib import Path

from hoshino import data_dir
from hoshino.command import uni_image, uni_text
from hoshino.types import MessageLike
from hoshino.util import aiohttpx
from hoshino.util.media import save_img_by_path
from hoshino.util.message import send_segments

from ..utils import Post as BasePost
from ..utils import PostMessage, clean_filename
from .sv import sv

NGA_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Referer": "https://bbs.nga.cn/",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate",
    "Upgrade-Insecure-Requests": "1",
}
# 附件相对路径（attachs.attachurl / [img] BBCode）统一拼这个前缀。
IMG_BASE = "https://img.nga.178.com/attachments"
API_URL = "https://bbs.nga.cn/read.php?tid={tid}&__output=11"
nga_img_dir = data_dir / "ngaimages"
nga_img_dir.mkdir(exist_ok=True)


class Post(BasePost):
    async def download_images(self) -> list[Path]:
        async def download_single_image(i: int, img_url: str) -> Path | None:
            try:
                content_part = clean_filename(self.content[:20])
                nickname_part = clean_filename(self.nickname)
                filename = f"{content_part}_{nickname_part}_{self.id}_{i}.jpg"
                filepath = nga_img_dir / filename
                result_path = await save_img_by_path(img_url, filepath, True, headers=NGA_HEADERS)
                if result_path:
                    return result_path
                sv.logger.error(f"Failed to save image {img_url}")
                return None
            except Exception:
                sv.logger.exception(f"Error downloading image {img_url}", exception=True)
                return None

        tasks = [download_single_image(i, img_url) for i, img_url in enumerate(self.images)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        saved: list[Path] = []
        for result in results:
            if isinstance(result, Path):
                saved.append(result)
            elif isinstance(result, Exception):
                sv.logger.error(f"Error in download task: {result}")
        return saved

    async def get_message(self, full: bool = False) -> PostMessage:
        imgs = await self.download_images() if full else []
        return PostMessage(
            text=self._build_text(),
            images=imgs,
        )

    def render_message(self, post_message: PostMessage) -> list[MessageLike]:
        messages: list[MessageLike] = []
        if post_message.text:
            messages.append(uni_text(post_message.text))
        messages.extend(uni_image(img) for img in post_message.images)
        return messages

    def get_referer(self) -> str:
        return "https://bbs.nga.cn/"

    def _build_text(self) -> str:
        title = f"\n标题：{self.title}" if self.title else ""
        return f"{self.nickname or 'NGA'} NGA~{title}\n----------\n{self.content}\n链接: {self.url}"


def clean_nga_text(text: str, max_length: int = 500) -> str:
    """清理 NGA 正文：图片标签移除、url 保留文字、quote 移除、格式标签去壳、HTML 标签清除。"""
    rules: list[tuple[str, str, int]] = [
        (r"\[img\][^\[\]]*\[/img\]", "", 0),
        (r"\[img\][^\[\]]*", "", 0),
        (r"\[url=[^\]]*\]([^\[]*?)\[/url\]", r"\1", 0),
        (r"\[url\]([^\[]*?)\[/url\]", r"\1", 0),
        (r"\[quote\].*?\[/quote\]", "", re.DOTALL),
        (r"\[(b|i|u)\](.*?)\[/\1\]", r"\2", re.DOTALL),
        (r"\[(color|size)=[^\]]*\](.*?)\[/\1\]", r"\2", re.DOTALL),
        (r"\[[^]]+\]", "", 0),
        # JSON API 的正文里混合 HTML（<br/> 等），一并清理
        (r"<br\s*/?>", "\n", re.I),
        (r"</?[a-zA-Z][^>]*>", "", 0),
        (r"\n{3,}", "\n\n", 0),
        (r"[ \t]+", " ", 0),
        (r"\n\s+\n", "\n\n", 0),
    ]
    for pattern, replacement, flags in rules:
        text = re.sub(pattern, replacement, text, flags=flags)
    text = text.strip()
    if len(text) > max_length:
        text = text[:max_length] + "..."
    return text


def _full_image_url(path: str) -> str:
    return f"{IMG_BASE}/{path.lstrip('/')}"


def _extract_images(row: dict) -> list[str]:
    """图片来源：attachs 附件列表（type=img）+ 正文 [img] BBCode，去重保序。"""
    urls: list[str] = []
    seen: set[str] = set()

    def add(candidate: str | None) -> None:
        if not candidate:
            return
        url = _full_image_url(candidate.strip())
        if url in seen:
            return
        seen.add(url)
        urls.append(url)

    attachs = row.get("attachs")
    if isinstance(attachs, list):
        for attach in attachs:
            if isinstance(attach, dict) and str(attach.get("type") or "") == "img":
                add(attach.get("attachurl"))
    for matched in re.finditer(r"\[img\]([^\[\]]*)\[/img\]", str(row.get("content") or "")):
        add(matched.group(1))
    return urls


async def _fetch_topic_data(tid: str) -> dict | None:
    """带 guestJs 挑战流程获取 ``__output=11`` 的 ``data`` 节点；失败返回 None。"""
    url = API_URL.format(tid=tid)
    response = await aiohttpx.get(url, headers=NGA_HEADERS, timeout=15.0)
    text = response.text or ""
    if response.status_code == 403 and "guestJs" in text:
        matched = re.search(r"guestJs=([^;'\"]+)", text)
        if not matched:
            sv.logger.error("nga: 挑战页未找到 guestJs")
            return None
        # 保留服务端 Set-Cookie（ngaPassportUid/lastvisit 等）+ guestJs 再重试。
        parts = [sc.split(";", 1)[0] for sc in response.headers.get_list("set-cookie")]
        cookies = "; ".join(parts) + f"; guestJs={matched.group(1)}"
        await asyncio.sleep(0.3)
        retry_url = f"{url}&rand={random.randint(0, 999)}"
        response = await aiohttpx.get(
            retry_url, headers={**NGA_HEADERS, "Cookie": cookies}, timeout=15.0
        )
        text = response.text or ""
    if response.status_code != 200:
        sv.logger.error(f"nga: 请求失败，状态码 {response.status_code}")
        return None
    try:
        payload = json.loads(text[text.index("{") :])
    except (ValueError, json.JSONDecodeError):
        sv.logger.error("nga: 响应不是 JSON，可能被风控")
        return None
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict) or not isinstance(data.get("__R"), list):
        sv.logger.error("nga: 响应缺少楼层数据 __R")
        return None
    return data


def _parse_topic(data: dict) -> Post | None:
    rows = data["__R"]
    if not rows or not isinstance(rows[0], dict):
        return None
    first = rows[0]
    users = data.get("__U") or {}
    user = users.get(str(first.get("authorid") or "")) or {}
    nickname = str(user.get("username") or user.get("nickname") or "")
    tid = str((data.get("__T") or {}).get("tid") or "")
    return Post(
        uid=nickname or str(first.get("authorid") or ""),
        id=tid,
        content=clean_nga_text(str(first.get("content") or "")),
        title=str((data.get("__T") or {}).get("subject") or ""),
        images=_extract_images(first),
        nickname=nickname,
        timestamp=float(first.get("postdatetimestamp") or 0),
        url=f"https://nga.178.com/read.php?tid={tid}",
    )


async def parse_nga(tid: str) -> Post | None:
    data = await _fetch_topic_data(tid)
    if data is None:
        return None
    post = _parse_topic(data)
    if post is None:
        sv.logger.error(f"nga: 无法解析帖子数据，tid: {tid}")
    return post


async def resolve_nga(name: str, url: str) -> bool:
    matched = re.search(r"tid=(\d+)", url)
    if not matched:
        return False
    post = await parse_nga(matched.group(1))
    if not post:
        sv.logger.error(f"{name} {url} parse error")
        return False
    post_message = await post.get_message(full=True)
    msgs = post.render_message(post_message)
    if not msgs:
        return False
    await asyncio.sleep(0.3)
    await send_segments(msgs)
    return True
