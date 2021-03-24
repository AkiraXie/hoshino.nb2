'''
Author: AkiraXie
Date: 2021-02-09 23:30:52
LastEditors: AkiraXie
LastEditTime: 2021-03-15 05:05:22
Description: 
Github: http://github.com/AkiraXie/
'''
from loguru import logger
from pytz import timezone
from hoshino.util import pic2b64
from io import BytesIO
from hoshino import aiohttpx, db_dir, MessageSegment
from PIL import Image
from bs4 import BeautifulSoup
import peewee as pw
from feedparser import FeedParserDict
import feedparser
from typing import List, Dict, Optional, Union
from datetime import datetime
import time
import os
BASE_URL = "https://rsshub.akiraxie.cc/"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


class Rss:
    def __init__(self, url: str, limit: int = 8) -> None:
        super().__init__()
        self.url = url
        self.limit = limit

    @classmethod
    async def new(cls, url: str, limit: int = 8) -> "Rss":
        '''
        `Rss` 类真正的构造函数
        '''
        self = cls(url, limit)
        ret = await aiohttpx.get(self.url, params={'limit': self.limit, 'timeout': 5})
        self.feed = feedparser.parse(ret.content)
        self.link = self.feed.feed.get('link','链接出错')
        return self

    @property
    def feed_entries(self) -> Optional[List]:
        feed = self.feed
        if len(feed.entries) != 0:
            return feed.entries
        else:
            return

    @property
    def has_entries(self) -> bool:
        return self.feed_entries is not None

    @staticmethod
    def format_time(entry: FeedParserDict, flag:bool=False) -> Union[datetime, str]:
        time_str = entry.get('updated_parsed', entry['published_parsed'])
        ts=time.mktime(time_str)
        dt = datetime.fromtimestamp(ts).replace(tzinfo=timezone('UTC')).astimezone(timezone('Asia/Shanghai'))
        return dt.strftime(DATE_FORMAT) if flag else dt

    @staticmethod
    def _get_rssdic(entry: FeedParserDict, flag: bool = False) -> Dict:
        ret = {'标题': entry.title,
               '链接': entry.link, }
        ret['时间'] = Rss.format_time(entry,True)
        if not flag:
            return ret
    
        soup = BeautifulSoup(entry.summary, "lxml")
        imglist = []
        videolist=[]
        ret['正文'] = soup.get_text()
        for i in soup.find_all('img'):
            imglist.append(str(MessageSegment.image(i['src'])))
        for v in soup.find_all('video'):
            poster=v['poster']
            video=v['src']
            videolist.append(MessageSegment.video(video))
            imglist.append(str(MessageSegment.image(poster)))
        ret['视频'] = videolist
        ret['图片'] = imglist
            

        return ret

    async def get_new_entry_info(self) -> Optional[Dict]:
        try:
            entries = self.feed_entries
            return Rss._get_rssdic(entries[0], True)
        except Exception as e:
            logger.exception(e)

    async def get_all_entry_info(self) -> Optional[List[Dict]]:
        try:
            ret = []
            entries = self.feed_entries
            lmt = min(self.limit, len(entries))
            for entry in entries[:lmt]:
                entrydic = self._get_rssdic(entry)
                ret.append(entrydic)
            return ret
        except Exception as e:
            logger.exception(e)

    async def get_interval_entry_info(self, otherdt: Union[str,datetime]) -> Optional[List[Dict]]:
        try:
            if isinstance(otherdt,str):
                otherdt=datetime.strptime(otherdt,DATE_FORMAT+'%z')
            otherdt=otherdt.replace(tzinfo=timezone('UTC')).astimezone(timezone('Asia/Shanghai'))
            ret = []
            entries = []
            for entry in self.feed_entries:
                dt = Rss.format_time(entry)
                if dt > otherdt:
                    entries.append(entry)
                else:
                    break
            if not entries:
                return None
            for entry in entries:
                entrydic = self._get_rssdic(entry, True)
                ret.append(entrydic)
            return ret
        except Exception as e:
            logger.exception(e)

    @property
    def last_update(self) -> Optional[datetime]:
        try:
            entries = self.feed_entries
            res = Rss.format_time(entries[0])
            return res
        except Exception as e:
            logger.exception(e)


db_path = os.path.join(db_dir, 'rssdata.db')
db = pw.SqliteDatabase(db_path)


class Rssdata(pw.Model):
    url = pw.TextField()
    name = pw.TextField()
    date = pw.DateTimeField()
    group = pw.IntegerField()

    class Meta:
        database = db
        primary_key = pw.CompositeKey('name', 'group')


if not os.path.exists(db_path):
    db.connect()
    db.create_tables([Rssdata])
    db.close()
