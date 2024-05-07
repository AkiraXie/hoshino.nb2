"""
Author: AkiraXie
Date: 2021-01-30 01:37:42
LastEditors: AkiraXie
LastEditTime: 2021-02-15 04:00:41
Description: 
Github: http://github.com/AkiraXie/
"""
from aiohttp import ClientSession
from multidict import CIMultiDictProxy
from yarl import URL
from loguru import logger
from json import loads


class BaseResponse:
    def __init__(
        self, url: URL, status_code: int, headers: CIMultiDictProxy[str], ok: bool
    ) -> None:
        self.url: URL = url
        self.status_code: int = status_code
        self.headers: CIMultiDictProxy[str] = headers
        self.ok: bool = ok


class Response(BaseResponse):
    def __init__(
        self,
        url: URL,
        content: bytes,
        status_code: int,
        headers: CIMultiDictProxy[str],
        ok: bool,
    ) -> None:
        super().__init__(url=url, status_code=status_code, headers=headers, ok=ok)
        self.content: bytes = content

    @property
    def json(self):
        try:
            return loads(self.content)
        except Exception as e:
            logger.exception(e)

    @property
    def text(self) -> str:
        try:
            return self.content.decode()
        except Exception as e:
            logger.exception(e)


async def get(url: str,*,cookies:dict = {}, **kwargs) -> Response:
    kwargs.setdefault("verify_ssl", False)
    kwargs.setdefault("timeout", 10)
    async with ClientSession(cookies=cookies) as session:
        async with session.get(url, **kwargs) as resp:
            res = Response(
                resp.url, await resp.read(), resp.status, resp.headers, resp.ok
            )
    return res


async def post(url: str, *args, cookies:dict = {},**kwargs) -> Response:
    kwargs.setdefault("verify_ssl", False)
    kwargs.setdefault("timeout", 10)
    async with ClientSession(cookies=cookies) as session:
        async with session.post(url, *args, **kwargs) as resp:
            res = Response(
                resp.url, await resp.read(), resp.status, resp.headers, resp.ok
            )
    return res


async def head(url: str, *args, **kwargs) -> BaseResponse:
    kwargs.setdefault("verify_ssl", False)
    kwargs.setdefault("timeout", 5)
    async with ClientSession() as session:
        async with session.head(url, *args, **kwargs) as resp:
            res = BaseResponse(resp.url, resp.status, resp.headers, resp.ok)
    return res
