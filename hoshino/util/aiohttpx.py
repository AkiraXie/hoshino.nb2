from typing import Any
from httpx import AsyncClient
import httpx
from httpx import URL
from loguru import logger
from json import loads


class BaseResponse:
    def __init__(
        self, url: URL, status_code: int, headers: httpx.Headers, _resp: httpx.Response
    ) -> None:
        self.url: URL = url
        self.status_code: int = status_code
        self.headers: httpx.Headers = headers
        self.ok: bool = 200 <= status_code < 300
        self._resp: httpx.Response = _resp


class Response(BaseResponse):
    def __init__(
        self,
        url: URL,
        content: bytes,
        status_code: int,
        headers: httpx.Headers,
        _resp: httpx.Response = None,
        text: str = None,
        cookies: dict = {},
    ) -> None:
        super().__init__(url=url, status_code=status_code, headers=headers, _resp=_resp)
        self.content: bytes = content
        self.cookies = cookies
        self.text: str = text

    @property
    def json(self) -> Any:
        return self._resp.json()


async def get(
    url: str, *, verify: bool = True, timeout=10, cookies: dict = {}, **kwargs
) -> Response:
    async with AsyncClient(
        cookies=cookies, timeout=httpx.Timeout(timeout), verify=verify
    ) as session:
        resp = await session.get(url, **kwargs)
        res = Response(
            resp.url,
            resp.content,
            resp.status_code,
            resp.headers,
            _resp=resp,
            text=resp.text,
            cookies=resp.cookies,
        )
    return res


async def post(
    url: str, verify: bool = True, timeout=10, cookies: dict = {}, **kwargs
) -> Response:
    async with AsyncClient(
        cookies=cookies, timeout=httpx.Timeout(timeout), verify=verify
    ) as session:
        resp = await session.post(url, **kwargs)
        res = Response(
            resp.url,
            resp.content,
            resp.status_code,
            resp.headers,
            _resp=resp,
            text=resp.text,
            cookies=resp.cookies,
        )
    return res


async def head(
    url: str, verify: bool = True, timeout=10, cookies: dict = {}, **kwargs
) -> BaseResponse:
    async with AsyncClient(
        cookies=cookies, timeout=httpx.Timeout(timeout), verify=verify
    ) as session:
        resp = await session.head(url, **kwargs)
        res = BaseResponse(resp.url, resp.status_code, resp.headers, _resp=resp)
    return res
