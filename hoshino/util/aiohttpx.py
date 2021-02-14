'''
Author: AkiraXie
Date: 2021-01-30 01:37:42
LastEditors: AkiraXie
LastEditTime: 2021-02-15 04:00:41
Description: 
Github: http://github.com/AkiraXie/
'''
from aiohttp import ClientSession
from typing import Optional
from loguru import logger
from json import loads


class BaseResponse:
    def __init__(self, status_code=None, headers=None) -> None:
        self.status_code: Optional[int] = status_code
        self.headers: Optional[dict] = headers


class Response(BaseResponse):
    def __init__(self, content=None, status_code=None, headers=None) -> None:
        super().__init__(status_code=status_code, headers=headers)
        self.content: Optional[bytes] = content

    @property
    def json(self):
        try:
            return loads(self.content)
        except Exception as e:
            logger.exception(e)

    @property
    def text(self):
        try:
            return self.content.decode()
        except Exception as e:
            logger.exception(e)


async def get(url: str, *args, **kwargs) -> Response:
    kwargs.setdefault('verify_ssl', False)
    async with ClientSession() as session:
        async with session.get(url, *args, **kwargs) as resp:
            return Response(await resp.read(), resp.status, resp.headers)


async def post(url: str, *args, **kwargs) -> Response:
    kwargs.setdefault('verify_ssl', False)
    async with ClientSession() as session:
        async with session.post(url, *args, **kwargs) as resp:
            return Response(await resp.read(), resp.status, resp.headers)


async def head(url: str, *args, **kwargs) -> BaseResponse:
    kwargs.setdefault('verify_ssl', False)
    async with ClientSession() as session:
        async with session.head(url, *args, **kwargs) as resp:
            return BaseResponse(resp.status, resp.headers)
