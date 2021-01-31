'''
Author: AkiraXie
Date: 2021-01-30 01:37:42
LastEditors: AkiraXie
LastEditTime: 2021-01-31 21:37:50
Description: 
Github: http://github.com/AkiraXie/
'''
from aiohttp import ClientSession
from typing import Optional



class BaseResponse:
    def __init__(self, content=None, text=None, json=None, status_code=None, headers=None) -> None:
        self.content: Optional[bytes] = content
        self.text: Optional[str] = text
        self.json: Optional[dict] = json
        self.status_code: Optional[int] = status_code
        self.headers: Optional[dict] = headers


async def get(url: str, *args, **kwargs) -> BaseResponse:
    async with ClientSession() as session:
        async with session.get(url,*args,**kwargs) as resp:
            return BaseResponse(await resp.read(), await resp.text(), await resp.json(content_type=None), resp.status, resp.headers)

async def post(url: str, *args, **kwargs) -> BaseResponse:
    async with ClientSession() as session:
        async with session.post(url,*args,**kwargs) as resp:
            return BaseResponse(await resp.read(), await resp.text(), await resp.json(content_type=None), resp.status, resp.headers)


async def head(url: str, *args, **kwargs) -> BaseResponse:
       async with ClientSession() as session:
        async with session.head(url,*args,**kwargs) as resp:
            return BaseResponse(status_code=resp.status, headers=resp.headers)
