'''
Author: AkiraXie
Date: 2021-02-11 00:00:55
LastEditors: AkiraXie
LastEditTime: 2021-02-11 01:11:24
Description: 
Github: http://github.com/AkiraXie/
'''
import abc
from bs4 import BeautifulSoup
from dataclasses import dataclass
from typing import List, Union
from hoshino.util import aiohttpx


@dataclass
class Item:
    idx: Union[str, int]
    content: str = ""
    link: str = ""
    time: str=""

    def __eq__(self, other):
        return self.idx == other.idx


class BaseSpider(abc.ABC):
    url = None
    src_name = None
    idx_cache = set()
    item_cache = []

    @classmethod
    async def get_response(cls) -> aiohttpx.BaseResponse:
        resp = await aiohttpx.get(cls.url)
        return resp

    @staticmethod
    @abc.abstractmethod
    async def get_items(resp: aiohttpx.BaseResponse) -> List[Item]:
        raise NotImplementedError

    @classmethod
    async def get_update(cls) -> List[Item]:
        resp = await cls.get_response()
        items = await cls.get_items(resp)
        updates = [ i for i in items if i.idx not in cls.idx_cache ]
        if updates:
            cls.idx_cache = set(i.idx for i in items)
            cls.item_cache = items
        return updates

    @classmethod
    def format_items(cls, items) -> str:
        msgs=[]
        for i,item in enumerate(items):
            msg=[f'News {i+1} | Time {item.time}',f'Title: {item.content}',f'Link: {item.link}','=========']
            msg='\n'.join(msg)
            msgs.append(msg)
        return f'{cls.src_name}新闻\n'+'\n'.join(msgs)



class SonetSpider(BaseSpider):
    url = "http://www.princessconnect.so-net.tw/news/"
    src_name = "台服官网"

    @staticmethod
    async def get_items(resp:aiohttpx.BaseResponse):
        soup = BeautifulSoup(resp.content, 'lxml')
        return [
            Item(idx=dd.a["href"],
                 content=f"{dd.text}",
                 link=f"www.princessconnect.so-net.tw{dd.a['href']}",
                 time=str(dd.previous_sibling.previous_sibling.get_text()).strip()[:10]
            ) for dd in soup.find_all("dd")
        ]



class BiliSpider(BaseSpider):
    url = "https://api.biligame.com/news/list?gameExtensionId=267&positionId=2&typeId=&pageNum=1&pageSize=5"
    src_name = "B服官网"

    @staticmethod
    async def get_items(resp:aiohttpx.BaseResponse):
        content = resp.json
        items = [
            Item(idx=n["id"],
                 content=f"{n['title']}",
                 link="game.bilibili.com/pcr/news.html#detail={id}".format_map(n),
                 time=f"{n['ctime'][:11]}"
            ) for n in content["data"]
        ]
        return items
