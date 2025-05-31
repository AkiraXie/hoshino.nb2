import asyncio
from typing import Any
from httpx import AsyncClient
import httpx
from httpx import URL
from loguru import logger
import simplejson
from hoshino import on_startup, on_shutdown
import ssl

_timeout = 5.0
_client = None
_client_unverified = None
_client_lock = asyncio.Lock()


@on_startup
async def init_httpx_client():
    global _client, _client_unverified
    _client = AsyncClient(
        timeout=httpx.Timeout(_timeout, read=_timeout * 3),
        limits=httpx.Limits(max_keepalive_connections=20, max_connections=100),
        verify=True,
    )

    unverified_context = ssl._create_unverified_context()
    unverified_context.check_hostname = False
    unverified_context.verify_mode = ssl.CERT_NONE

    _client_unverified = AsyncClient(
        timeout=httpx.Timeout(_timeout, read=_timeout * 3),
        limits=httpx.Limits(max_keepalive_connections=20, max_connections=100),
        verify=unverified_context,
    )
    logger.info("HTTPX clients initialized successfully.")


@on_shutdown
async def close_httpx_client():
    global _client, _client_unverified
    if _client:
        await _client.aclose()
        _client = None
    if _client_unverified:
        await _client_unverified.aclose()
        _client_unverified = None
    logger.info("HTTPX clients closed successfully.")


async def get_client(verify_ssl: bool = True):
    global _client, _client_unverified
    target_client = _client if verify_ssl else _client_unverified

    if target_client is None:
        async with _client_lock:
            if (verify_ssl and _client is None) or (
                not verify_ssl and _client_unverified is None
            ):
                await init_httpx_client()

    return _client if verify_ssl else _client_unverified


class BaseResponse:
    def __init__(
        self,
        url: URL,
        status_code: int,
        headers: httpx.Headers,
        _resp: httpx.Response | None,
    ) -> None:
        self.url: URL = url
        self.status_code: int = status_code
        self.headers: httpx.Headers = headers
        self.ok: bool = 200 <= status_code < 300
        self._resp = _resp


class Response(BaseResponse):
    def __init__(
        self,
        url: URL,
        content: bytes,
        status_code: int,
        headers: httpx.Headers,
        _resp: httpx.Response | None = None,
        text: str | None = None,
        cookies: httpx.Cookies | None = None,
    ) -> None:
        super().__init__(url=url, status_code=status_code, headers=headers, _resp=_resp)
        self.content: bytes = content
        self.cookies = cookies
        self.text = text

    @property
    def json(self) -> Any:
        return simplejson.loads(self.content)


async def get(
    url: str, cookies: dict = {}, timeout: float = 5.0, verify: bool = True, **kwargs
) -> Response:
    try:
        client = await get_client(verify_ssl=verify)
        if not client:
            raise RuntimeError("HTTPX client is not initialized.")
        if timeout is not None:
            kwargs["timeout"] = timeout
        resp = await client.get(url, cookies=cookies, **kwargs)
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
    except Exception as e:
        logger.error(
            f"GET request failed - URL: {url}, params: {kwargs}, cookies: {cookies},error: {e}"
        )
        raise


async def post(
    url: str, cookies: dict = {}, timeout: float = 5.0, verify: bool = True, **kwargs
) -> Response:
    try:
        client = await get_client(verify_ssl=verify)
        if not client:
            raise RuntimeError("HTTPX client is not initialized.")
        if timeout is not None:
            kwargs["timeout"] = timeout
        resp = await client.post(url, cookies=cookies, **kwargs)
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
    except Exception as e:
        logger.error(
            f"POST request failed - URL: {url}, params: {kwargs}, cookies: {cookies}, error: {e}"
        )
        raise


async def head(
    url: str, timeout: float = 5.0, verify: bool = True, **kwargs
) -> BaseResponse:
    try:
        client = await get_client(verify_ssl=verify)
        if not client:
            raise RuntimeError("HTTPX client is not initialized.")
        if timeout is not None:
            kwargs["timeout"] = timeout
        resp = await client.head(url, **kwargs)
        res = BaseResponse(resp.url, resp.status_code, resp.headers, _resp=resp)
        return res
    except Exception as e:
        logger.error(f"HEAD request failed - URL: {url}, params: {kwargs},  error: {e}")
        raise
