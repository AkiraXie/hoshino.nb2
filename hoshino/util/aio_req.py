'''
Author: AkiraXie
Date: 2021-01-30 00:05:12
LastEditors: AkiraXie
LastEditTime: 2021-01-30 13:04:38
Description: 
Github: http://github.com/AkiraXie/
'''
from aiohttp import request
from hoshino.typing import CIMultiDictProxy,Any


async def aio_get_json(url: str, params=None, content_type: str = 'application/json', **kw) -> Any:
    async with request('get', url, params=params, **kw) as rp:
        return await rp.json(content_type=content_type)


async def aio_get_content(url: str, params=None, **kw) -> bytes:
    async with request('get', url, params=params, **kw) as rp:
        return await rp.read()


async def aio_get_text(url: str, params=None, **kw) -> str:
    async with request('get', url, params=params, **kw) as rp:
        return await rp.text()

async def aio_get_status(url: str, params=None, **kw) -> int:
    async with request('head', url, params=params, **kw) as rp:
        return rp.status
async def aio_post_json(url: str, params=None, content_type: str = 'application/json', **kw) -> Any:
    async with request('post', url, params=params, **kw) as rp:
        return await rp.json(content_type=content_type)


async def aio_get_content(url: str, params=None, **kw) -> bytes:
    async with request('post', url, params=params, **kw) as rp:
        return await rp.read()


async def aio_get_text(url: str, params=None, **kw) -> str:
    async with request('post', url, params=params, **kw) as rp:
        return await rp.text()


async def aio_head_headers(url: str, params=None, **kw) -> CIMultiDictProxy[str]:
    async with request('head', url, params=params, **kw) as rp:
        return rp.headers()


async def aio_head_status(url: str, params=None, **kw) -> int:
    async with request('head', url, params=params, **kw) as rp:
        return rp.status
