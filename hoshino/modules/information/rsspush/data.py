'''
Author: AkiraXie
Date: 2021-02-09 23:30:52
LastEditors: AkiraXie
LastEditTime: 2021-02-13 20:19:36
Description: 
Github: http://github.com/AkiraXie/
'''
from loguru import logger
from hoshino.util import concat_pic, pic2b64
from io import BytesIO
from hoshino import aiohttpx, db_dir, MessageSegment
from PIL import Image
from bs4 import BeautifulSoup
import peewee as pw
from feedparser import FeedParserDict
import feedparser
from typing import List, Dict, Optional
from datetime import datetime, timedelta
import time
import os
BASE_URL = "https://rsshub.akiraxie.me/"


def gen_rss_pic(imglist: List[Image.Image]):
    num = len(imglist)
    size = 400
    des = Image.new('RGBA', (num*size, size), (255, 255, 255, 255))
    for i, img in enumerate(imglist):
        des.paste(img, (i*size, 0), img)
    return des


class Rss:
    def __init__(self, url: str, limit: int = 1) -> None:
        super().__init__()
        self.url = url
        self.limit = limit

    @property
    async def feed(self) -> FeedParserDict:
        ret = await aiohttpx.get(self.url, params={'limit': self.limit, 'timeout': 5})
        return feedparser.parse(ret.content)

    @property
    async def feed_entries(self) -> Optional[List]:
        feed = await self.feed
        if len(feed.entries) != 0:
            return feed.entries
        else:
            return

    @property
    async def link(self) -> str:
        feed = await self.feed
        return feed.feed.link

    @property
    async def has_entries(self) -> bool:
        return (await self.feed_entries) is not None

    @staticmethod
    def format_time(timestr: str) -> str:
        try:
            struct_time = time.strptime(timestr, '%a, %d %b %Y %H:%M:%S %Z')
        except:
            struct_time = time.strptime(timestr, '%Y-%m-%dT%H:%M:%SZ')
        dt = datetime.fromtimestamp(time.mktime(struct_time))
        return str(dt+timedelta(hours=8))

    @staticmethod
    async def _get_rssdic(entry: FeedParserDict, flag: bool = False) -> Dict:
        ret = {'标题': entry.title,
               '时间': entry.updated,
               '链接': entry.link, }
        try:
            ret['时间'] = Rss.format_time(ret['时间'])
        except:
            pass
        if flag:
            soup = BeautifulSoup(entry.summary, "lxml")
            imglist = []
            ret['正文'] = soup.get_text()
            for i in soup.find_all('img'):
                img = await aiohttpx.get(i['src'], timeout=5)
                img = Image.open(BytesIO(img.content)).convert('RGBA')
                if img.width < 400 or img.height < 400:
                    continue
                center=(img.width//2,img.height//2)
                new_size=(center[0]-200,center[1]-200,center[0]+200,center[1]+200)
                img=img.crop(new_size)
                imglist.append(img)
            imglen = min(len(imglist),9)
            pics = []
            if imglen == 0:
                res = ""
            else:
                for i in range(0, imglen, 3):
                    j = min(imglen, i+3)
                    pics.append(gen_rss_pic(imglist[i:j]))
                res = pic2b64(concat_pic(pics))
                res = str(MessageSegment.image(res))
            ret['图片'] = res

        return ret

    async def get_new_entry_info(self) -> Optional[Dict]:
        try:
            entries = await self.feed_entries
            return await Rss._get_rssdic(entries[0], True)
        except Exception as e:
            logger.exception(e)

    async def get_all_entry_info(self) -> Optional[List[Dict]]:
        try:
            ret = []
            entries = await self.feed_entries
            lmt = min(self.limit, len(entries))
            for entry in entries[:lmt]:
                entrydic = await self._get_rssdic(entry)
                ret.append(entrydic)
            return ret
        except Exception as e:
            logger.exception(e)

    @property
    async def last_update(self) -> Optional[str]:
        try:
            entries = await self.feed_entries
            res= entries[0].updated
            return res
        except Exception as e:
            logger.exception(e)


db_path = os.path.join(db_dir, 'rssdata.db')
db = pw.SqliteDatabase(db_path)


class Rssdata(pw.Model):
    url = pw.TextField()
    name = pw.TextField()
    date = pw.TextField()
    group = pw.IntegerField()

    class Meta:
        database = db
        primary_key = pw.CompositeKey('url', 'group')


if not os.path.exists(db_path):
    db.connect()
    db.create_tables([Rssdata])
    db.close()
