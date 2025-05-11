import asyncio
from dataclasses import dataclass
from datetime import datetime
import functools
import json
from typing import Dict, List,Optional
import peewee as pw
import os
from hoshino import db_dir, Message,Service,MessageSegment
from hoshino.util import  aiohttpx
from lxml.etree import HTML
from yarl import URL
from urllib.parse import unquote
from httpx import AsyncClient
from hoshino.util.playwrights import get_weibo_screenshot
sv = Service("weibo", enable_on_default=False,visible=False)

_HEADER = {
    "accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,"
        "*/*;q=0.8,application/signed-exchange;v=b3;q=0.9"
    ),
    "accept-language": "zh-CN,zh;q=0.9",
    "authority": "m.weibo.cn",
    "cache-control": "max-age=0",
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "same-origin",
    "sec-fetch-site": "same-origin",
    "upgrade-insecure-requests": "1",
    "user-agent": (
        "Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/89.0.4389.72 "
        "Mobile Safari/537.36"
    ),
}

@dataclass
class Post:
    """最通用的Post，理论上包含所有常用的数据

    对于更特殊的需要，可以考虑另外实现一个Post
    """
    """来源平台"""
    uid: str
    """用户ID"""
    id: str
    """微博ID"""
    content: str
    """文本内容"""
    title: str | None = None
    """标题"""
    images: list[str | bytes ] | None = None
    """图片列表"""
    timestamp: float | None = None
    """发布/获取时间戳, 秒"""
    url: str | None = None
    """来源链接"""
    nickname: str | None = None
    """发布者昵称"""
    description: str | None = None
    """发布者个性签名等"""
    repost: "Post | None" = None
    """转发的Post"""
    async def get_msg_with_screenshot(self) -> list[Message]:
        """获取消息"""
        msg = []
        immsg = []
        if self.repost:
            if self.repost.images:
                for img in self.repost.images:
                    immsg.append(MessageSegment.image(img))
        if self.images:
            for img in self.images:
                immsg.append(MessageSegment.image(img))
        if not immsg:
            if self.nickname:
                msg.append(self.nickname+ "微博~")
            if self.id:
                ms = await get_weibo_screenshot(self.id)
                if ms:
                    msg.append(str(ms))
                else:
                    return self.get_msg()
            if self.url:
                msg.append("详情: "+self.url)
            res = [Message('\n'.join(msg))]
            return res
        else:
            return self.get_msg()
    def get_msg(self) -> list[Message]:
        """获取消息"""
        msg = []
        immsg = []
        if self.nickname:
            msg.append(self.nickname+ "微博~")
        if self.content:
            msg.append(self.content)
        if self.repost:
            msg.append("------------")
            msg.append("转发自 "+ self.repost.nickname+ ":")
            msg.append(self.repost.content)
            msg.append("转发详情: "+self.repost.url)
            msg.append("------------")
            if self.repost.images:
                for img in self.repost.images:
                    immsg.append(MessageSegment.image(img))

        if self.images:
            for img in self.images:
                immsg.append(MessageSegment.image(img))
        
        if self.url:
            msg.append("详情: "+self.url)
        res = [Message("\n".join(msg))]
        if immsg:
            for i in immsg:
                res.append(Message(i))
        return res
    

async def get_sub_list(target: str,ts:float=0.0,keywords:list[str] = list()) -> list[Post]:
    header = {"Referer": f"https://m.weibo.cn/u/{target}", "MWeibo-Pwa": "1", "X-Requested-With": "XMLHttpRequest"}
    header.update(_HEADER)
    params = {"containerid": "107603" + target}
    res = await aiohttpx.get("https://m.weibo.cn/api/container/getIndex?", headers=header, params=params, timeout=4.0)
    res_data = res.json
    if not res_data["ok"] and res_data["msg"] != "这里还没有内容":
        return []

    def custom_filter(d) -> bool:
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
        return d["card_type"] == 9 and b and kb
    def cmp(d1,d2) -> bool:
        created1 = d1["mblog"]["created_at"]
        created2 = d2["mblog"]["created_at"]
        t1 = datetime.strptime(created1, "%a %b %d %H:%M:%S %z %Y").timestamp()
        t2 = datetime.strptime(created2, "%a %b %d %H:%M:%S %z %Y").timestamp()
        return t1-t2
    k = functools.cmp_to_key(cmp)
    l=list(filter(custom_filter, res_data["data"]["cards"]))
    l.sort(key=k)
    if not l:
        return []
    res = []
    for i in l:
        post = await parse_weibo_card(i)
        if post.timestamp > ts:
            res.append(post)
    return res

async def get_sub_new(target: str,ts:float=0.0,keywords:list[str] = list()) -> Optional[Post]:
    header = {"Referer": f"https://m.weibo.cn/u/{target}", "MWeibo-Pwa": "1", "X-Requested-With": "XMLHttpRequest"}
    header.update(_HEADER)
    params = {"containerid": "107603" + target}
    res = await aiohttpx.get("https://m.weibo.cn/api/container/getIndex?", headers=header, params=params, timeout=4.0)
    res_data = res.json
    if not res_data["ok"] and res_data["msg"] != "这里还没有内容":
        return []

    def custom_filter(d) -> bool:
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
        return d["card_type"] == 9 and b and kb
    def cmp(d1,d2) -> bool:
        created1 = d1["mblog"]["created_at"]
        created2 = d2["mblog"]["created_at"]
        t1 = datetime.strptime(created1, "%a %b %d %H:%M:%S %z %Y").timestamp()
        t2 = datetime.strptime(created2, "%a %b %d %H:%M:%S %z %Y").timestamp()
        return t1-t2
    k = functools.cmp_to_key(cmp)
    l=list(filter(custom_filter, res_data["data"]["cards"]))
    if not l:
        return None
    l.sort(key=k, reverse=True)
    post = await parse_weibo_card(l[0])

    return post

async def _get_long_weibo(weibo_id: str) -> dict:
    try:
        weibo_info = await aiohttpx.get(
            "https://m.weibo.cn/statuses/extend",
            params={"id": weibo_id},
            headers=_HEADER,
        )
        weibo_info = weibo_info.json
        if not weibo_info or weibo_info["ok"] != 1:
            return {}
        return weibo_info["data"]
    except (KeyError, TimeoutError):
        sv.logger.info(f"detail message error: https://m.weibo.cn/detail/{weibo_id}")
    return {}

def _get_text(raw_text: str) -> str:
        text = raw_text.replace("<br/>", "\n").replace("<br />", "\n")
        selector = HTML(text, parser=None)
        if selector is None:
            return text
        url_elems = selector.xpath("//a[@href]/span[@class='surl-text']")
        for br in selector.xpath("br"):
            br.tail = "\n" + br.tail
        for elem in url_elems:
            url = elem.getparent().get("href")
            if (
                not elem.text.startswith("#")
                and not elem.text.endswith("#")
                and (url.startswith("https://weibo.cn/sinaurl?u=") or url.startswith("https://video.weibo.com"))
            ):
                url = unquote(url.replace("https://weibo.cn/sinaurl?u=", ""))
                elem.text = f"{elem.text}( {url} )"
        return selector.xpath("string(.)")

async def _parse_weibo_card(info: dict) -> Post:
    if info["isLongText"] or info["pic_num"] > 9:
        info["text"] = (await _get_long_weibo(info["mid"]))["longTextContent"]
    parsed_text = _get_text(info["text"])
    raw_pics_list = info.get("pics", [])
    pic_urls = [img["large"]["url"] for img in raw_pics_list]
    # # 视频cover
    # if "page_info" in info and info["page_info"].get("type") == "video":
    #     crop_url = info["page_info"]["page_pic"]["url"]
    #     pic_urls.append(
    #         f"{URL(crop_url).scheme}://{URL(crop_url).host}/large/{info['page_info']['page_pic']['pid']}"
    #     )
    # pics = []
    # for pic_url in pic_urls:
    #     h = _HEADER.copy()
    #     h["referer"] = "https://weibo.com"
    #     async with AsyncClient(headers=h,follow_redirects=True) as client:
    #         res = await client.get(pic_url)
    #         res.raise_for_status()
    #         pics.append(res.content)
    detail_url = f"https://weibo.com/{info['user']['id']}/{info['bid']}"
    ts = info["created_at"]
    created_at = datetime.strptime(ts, "%a %b %d %H:%M:%S %z %Y")
    return Post(
        uid=info["user"]["id"],
        id=info["mid"],
        timestamp=created_at.timestamp(),
        content=parsed_text,
        url=detail_url,
        images=pic_urls,
        nickname=info["user"]["screen_name"],
    )

async def parse_weibo_card(raw: dict) -> Post:
    info = raw["mblog"]
    post = await _parse_weibo_card(info)
    if "retweeted_status" in info:
        post.repost = await _parse_weibo_card(info["retweeted_status"])
    return post

db_path = os.path.join(db_dir, "weibodata.db")
db = pw.SqliteDatabase(db_path)
class WeiboDB(pw.Model):
    uid = pw.TextField()
    group = pw.IntegerField()
    time = pw.FloatField()
    name = pw.TextField()
    keyword = pw.TextField(default="")
    class Meta:
        database = db
        primary_key = pw.CompositeKey("uid", "group")

if not os.path.exists(db_path):
    db.connect()
    db.create_tables([WeiboDB])
    db.close()