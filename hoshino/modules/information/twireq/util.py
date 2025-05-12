import asyncio
import os

import peewee as pw
from hoshino import Message, MessageSegment, db_dir, img_dir
from nonebot.log import logger
from hoshino.typing import List, Optional
from hoshino.util import aiohttpx, save_img, random_modify_pixel
from PIL import Image

headers = {
    "Authorization": "Bearer AAAAAAAAAAAAAAAAAAAAAFdRVQEAAAAAsOIu8wyV5KfjsXkCjdD4jfmEJF0"
    "%3D7aB2up2cXoThqTdOSNjh6TPTwL6nTIKuaZOo9Y973cSSMB1jKh",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/76.0.3809.100 Safari/537.36",
}

db_path = os.path.join(db_dir, "twitters.db")
db = pw.SqliteDatabase(db_path)
id_url = "https://api.twitter.com/2/users/{id}"
lookup_url = "https://api.twitter.com/2/users/by/username/{name}"
timeline_url = "https://api.twitter.com/2/users/{uid}/tweets"
tweets_url = "https://api.twitter.com/2/tweets/{tid}"


class TwitterDB(pw.Model):
    uid = pw.BigIntegerField()
    gid = pw.BigIntegerField()
    uname = pw.TextField()
    name = pw.TextField()
    tid = pw.BigIntegerField()

    class Meta:
        database = db
        primary_key = pw.CompositeKey("uid", "gid")


class Tweet:
    def __init__(
        self,
        tid: int,
        uname: str,
        name: str,
        text: str,
        media: List[str],
        rt: bool = False,
    ) -> None:
        self.tid = tid
        self.text = text
        self.uname = uname
        self.name = name
        self.url = f"https://twitter.com/{uname}/status/{tid}"
        self.tstr = f"TID: {tid}"
        self.media = media
        self.rt = rt

    def get_msg(self) -> Message:
        a = "Retweet" if self.rt else "Tweet"
        msg = ["{} {} Tweeter:".format(self.uname, a), self.text, self.url]
        if self.media:
            for m in self.media:
                msg.append(str(MessageSegment.image(m)))
        return Message("\n".join(msg))


async def expire_user(uid: int):
    url = id_url.format(id=uid)
    res = await aiohttpx.get(url, headers=headers)
    j = res.json
    d = j.get("data")
    return not d


async def lookup_user(name: str):
    url = lookup_url.format(name=name)
    res = await aiohttpx.get(url, headers=headers)
    j = res.json
    return int(j["data"]["id"]), str(j["data"]["name"]), str(j["data"]["username"])


params = {
    # "exclude": "replies",
    "max_results": 10,
    "expansions": "author_id,attachments.media_keys,referenced_tweets.id,referenced_tweets.id.author_id",
    "user.fields": "name,id,username",
    "media.fields": "url,type",
}


async def get_new_tweetid(uid: int) -> int:
    url = timeline_url.format(uid=uid)
    res = await aiohttpx.get(
        url, headers=headers, params={"max_results": 5, "exclude": "replies"}
    )
    if not res.json or not res.json.get("data"):
        return 0
    return int(res.json["data"][0]["id"])


async def get_tweet(tid: str):
    url = tweets_url.format(tid=tid)
    p = params.copy()
    p.pop("max_results")
    p.pop("exclude")
    try:
        res = await aiohttpx.get(url, headers=headers, params=p)
    except Exception as e:
        logger.exception(f"tweet request failed:\n{e}")
        return None
    res = res.json
    if not res.get("data"):
        return None
    user: dict = res["includes"]["users"][0]
    name = user["name"]
    uname = user["username"]
    text = res["data"]["text"]
    item = res["data"]
    includes = res["includes"]
    mediaa = includes.get("media")
    rts = includes.get("tweets")
    users = includes.get("users")
    item = res["data"]
    tempdic = {"rt": False}
    rt = item.get("referenced_tweets")
    if rt:
        tempdic["rid"] = rt[-1]["id"]
        tempdic["rt"] = True
    at = item.get("attachments")
    if at:
        media_keys = at.get("media_keys")
        tempdic["urls"] = []
    else:
        media_keys = []
    if mediaa:
        for md in mediaa:
            if md["media_key"] in media_keys:
                iurl = md.get("url")
                if iurl:
                    tempdic["urls"].append(iurl)
    if rts:
        for rtt in rts:
            if rtt["id"] == tempdic.get("rid", ""):
                tempdic["aid"] = rtt["author_id"]
                break
    if users:
        for ur in users:
            if ur["id"] == tempdic.get("aid", ""):
                tempdic["rname"] = ur["username"]
                break
    ttid = item["id"]
    tid = int(item["id"])
    text = item["text"]
    rtt = tempdic.get("rt", False)
    rid = tempdic.get("rid", ttid)
    rname = tempdic.get("rname", uname)
    mediass = tempdic.get("urls", [])
    iname = f"tweet@{rname}:{rid}"
    v = 0
    for i, img in enumerate(mediass):
        imname = iname + f"_{i}.jpg"
        path = os.path.abspath(img_dir + "/" + imname)
        if os.path.exists(path):
            img = Image.open(path)
            random_modify_pixel(img)
            img.close()
            mediass[i] = "file:///" + path
            v += 1
            continue
        for k in range(2):
            try:
                await save_img(img, imname)
                mediass[i] = "file:///" + path
                break
            except Exception as e:
                logger.exception(f"保存图片{imname}失败:\n{e}")
            await asyncio.sleep(0.15)
    tweet = Tweet(int(tid), uname, name, text, mediass, rtt)
    return tweet


async def get_tweets(uid: int, ptid: Optional[int] = None) -> List["Tweet"]:
    url = timeline_url.format(uid=uid)
    dic = params.copy()
    if ptid:
        dic["since_id"] = ptid
    else:
        dic["max_results"] = 5
    try:
        res = await aiohttpx.get(url, headers=headers, params=dic)
    except Exception as e:
        logger.exception(f"tweet request failed:\n{e}")
        return []

    res = res.json
    if not res.get("data"):
        return []
    user: dict = res["includes"]["users"][0]
    name = user["name"]
    uname = user["username"]
    data = res["data"]
    tweets = []
    maps = {}
    includes = res["includes"]
    mediaa = includes.get("media")
    users = res["includes"].get("users")
    rts = res["includes"].get("tweets")
    for item in data:
        tempdic = {"rt": False}
        rt = item.get("referenced_tweets")
        if rt:
            tempdic["rid"] = rt[-1]["id"]
            tempdic["rt"] = True
        at = item.get("attachments")
        if at:
            media_keys = at.get("media_keys")
            tempdic["urls"] = []
        else:
            media_keys = []
        if mediaa:
            for md in mediaa:
                if md["media_key"] in media_keys:
                    iurl = md.get("url")
                    if iurl:
                        tempdic["urls"].append(iurl)
        if rts:
            for rtt in rts:
                if rtt["id"] == tempdic.get("rid", ""):
                    tempdic["aid"] = rtt["author_id"]
                    break
        if users:
            for ur in users:
                if ur["id"] == tempdic.get("aid", ""):
                    tempdic["rname"] = ur["username"]
                    break
        maps[item["id"]] = tempdic.copy()
    for item in data:
        ttid = item["id"]
        tid = int(item["id"])
        text = item["text"]
        tmpdic = maps[ttid]
        rt = tmpdic.get("rt", False)
        rid = tmpdic.get("rid", ttid)
        rname = tmpdic.get("rname", uname)
        iname = f"tweet@{rname}:{rid}"
        mediass = tmpdic.get("urls", [])
        v = 0
        for i, img in enumerate(mediass):
            imname = iname + f"_{i}.jpg"
            path = os.path.abspath(img_dir + "/" + imname)
            if os.path.exists(path):
                v += 1
                continue
            for k in range(2):
                try:
                    await save_img(img, imname)
                    mediass[i] = "file:///" + path
                    break
                except Exception as e:
                    logger.exception(f"保存图片{imname}失败:\n{e}")
                await asyncio.sleep(0.25)
        if v != len(mediass) or ptid is None:
            twt = Tweet(tid, uname, name, text, mediass, rt)
            tweets.append(twt)
    return tweets


if not os.path.exists(db_path):
    db.connect()
    db.create_tables([TwitterDB])
    db.close()
