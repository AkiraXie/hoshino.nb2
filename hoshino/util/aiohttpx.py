from httpx import AsyncClient
import httpx
from httpx import URL
from loguru import logger
from json import loads


class BaseResponse:
    def __init__(self, url: URL, status_code: int, headers: httpx.Headers) -> None:
        self.url: URL = url
        self.status_code: int = status_code
        self.headers: httpx.Headers = headers
        self.ok: bool = 200 <= status_code < 300


class Response(BaseResponse):
    def __init__(
        self,
        url: URL,
        content: bytes,
        status_code: int,
        headers: httpx.Headers,
        cookies: dict = {},
    ) -> None:
        super().__init__(url=url, status_code=status_code, headers=headers)
        self.content: bytes = content
        self.cookies = cookies

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


async def get(url: str, *, timeout=10, cookies: dict = {}, **kwargs) -> Response:
    async with AsyncClient(cookies=cookies, timeout=httpx.Timeout(timeout)) as session:
        resp = await session.get(url, **kwargs)
        res = Response(
            resp.url, resp.content, resp.status_code, resp.headers, cookies=resp.cookies
        )
    return res


async def post(url: str, *args, timeout=10, cookies: dict = {}, **kwargs) -> Response:
    async with AsyncClient(cookies=cookies, timeout=httpx.Timeout(timeout)) as session:
        resp = await session.post(url, **kwargs)
        res = Response(
            resp.url, resp.content, resp.status_code, resp.headers, cookies=resp.cookies
        )
    return res


async def head(
    url: str, *args, timeout=10, cookies: dict = {}, **kwargs
) -> BaseResponse:
    async with AsyncClient(cookies=cookies, timeout=httpx.Timeout(timeout)) as session:
        resp = await session.head(url, **kwargs)
        res = BaseResponse(resp.url, resp.status_code, resp.headers)
    return res
