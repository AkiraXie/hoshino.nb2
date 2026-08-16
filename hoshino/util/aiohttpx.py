import asyncio
import os
import ssl
from collections.abc import Mapping
from typing import Any

import httpx
import simplejson
from httpx import URL, AsyncClient
from loguru import logger

from hoshino.core.hooks import on_shutdown, on_startup

from .urls import redact_url

_timeout = 5.0
_client = None
_client_unverified = None
_client_lock = asyncio.Lock()
_pool_size = max(1, (os.cpu_count() or 4) // 2)
_req_semaphore: asyncio.Semaphore | None = None


def _response_status(error: Exception) -> int | None:
    """从异常中提取 HTTP 状态码（若已收到响应）；请求未发出时为 None。"""
    response = getattr(error, "response", None)
    return getattr(response, "status_code", None)


def _header_keys(kwargs: dict[str, Any]) -> list[str]:
    """失败日志只输出 header 键名列表，不输出 header 值（可能含凭据）。"""
    headers = kwargs.get("headers", {})
    return sorted(headers) if isinstance(headers, Mapping) else []


@on_startup
async def init_httpx_client():
    global _client, _client_unverified, _req_semaphore
    _client = AsyncClient(
        timeout=httpx.Timeout(_timeout, read=_timeout * 3),
        limits=httpx.Limits(max_keepalive_connections=20, max_connections=100),
        verify=True,
    )

    # verify=False 客户端刻意提供 unverified context（内部接口信任场景）。
    unverified_context = ssl._create_unverified_context()  # noqa: S323, SLF001
    unverified_context.check_hostname = False
    unverified_context.verify_mode = ssl.CERT_NONE

    _client_unverified = AsyncClient(
        timeout=httpx.Timeout(_timeout, read=_timeout * 3),
        limits=httpx.Limits(max_keepalive_connections=20, max_connections=100),
        verify=unverified_context,
    )
    _req_semaphore = asyncio.Semaphore(_pool_size)
    logger.info("HTTPX clients initialized successfully.")


@on_shutdown
async def close_httpx_client():
    global _client, _client_unverified, _req_semaphore
    if _client:
        await _client.aclose()
        _client = None
    if _client_unverified:
        await _client_unverified.aclose()
        _client_unverified = None
    _req_semaphore = None
    logger.info("HTTPX clients closed successfully.")


async def get_client(verify_ssl: bool = True):
    global _client, _client_unverified, _req_semaphore
    target_client = _client if verify_ssl else _client_unverified

    if target_client is None:
        async with _client_lock:
            if (verify_ssl and _client is None) or (not verify_ssl and _client_unverified is None):
                await init_httpx_client()

    if _req_semaphore is None:
        _req_semaphore = asyncio.Semaphore(_pool_size)

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
        self.ok: bool = 200 <= status_code < 300 or status_code == 304
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

    def raise_for_status(self):
        self._resp.raise_for_status()

    @property
    def json(self) -> Any:
        if self._resp.encoding:
            return simplejson.loads(self.content, encoding=self._resp.encoding)
        return simplejson.loads(self.content)


async def get(
    url: str, cookies: dict | None = None, timeout: float = 5.0, verify: bool = True, **kwargs
) -> Response:
    if cookies is None:
        cookies = {}
    try:
        client = await get_client(verify_ssl=verify)
        if not client:
            raise RuntimeError("HTTPX client is not initialized.")  # noqa: TRY301  # 自身校验：未初始化属调用方错误，仍走统一日志后抛出
        if timeout is not None:
            kwargs["timeout"] = timeout
        async with _req_semaphore:
            resp = await client.get(url, cookies=cookies, **kwargs)
        return Response(
            resp.url,
            resp.content,
            resp.status_code,
            resp.headers,
            _resp=resp,
            text=resp.text,
            cookies=resp.cookies,
        )
    except Exception as error:
        logger.exception(
            "GET request failed - url: {}, status: {}, header keys: {}, error: {}",
            redact_url(url),
            _response_status(error),
            _header_keys(kwargs),
            type(error).__name__,
        )
        raise


async def post(
    url: str, cookies: dict | None = None, timeout: float = 5.0, verify: bool = True, **kwargs
) -> Response:
    if cookies is None:
        cookies = {}
    try:
        client = await get_client(verify_ssl=verify)
        if not client:
            raise RuntimeError("HTTPX client is not initialized.")  # noqa: TRY301  # 自身校验：未初始化属调用方错误，仍走统一日志后抛出
        if timeout is not None:
            kwargs["timeout"] = timeout
        async with _req_semaphore:
            resp = await client.post(url, cookies=cookies, **kwargs)
        return Response(
            resp.url,
            resp.content,
            resp.status_code,
            resp.headers,
            _resp=resp,
            text=resp.text,
            cookies=resp.cookies,
        )
    except Exception as error:
        logger.exception(
            "POST request failed - url: {}, status: {}, header keys: {}, error: {}",
            redact_url(url),
            _response_status(error),
            _header_keys(kwargs),
            type(error).__name__,
        )
        raise


async def head(url: str, timeout: float = 5.0, verify: bool = True, **kwargs) -> BaseResponse:
    try:
        client = await get_client(verify_ssl=verify)
        if not client:
            raise RuntimeError("HTTPX client is not initialized.")  # noqa: TRY301  # 自身校验：未初始化属调用方错误，仍走统一日志后抛出
        if timeout is not None:
            kwargs["timeout"] = timeout
        async with _req_semaphore:
            resp = await client.head(url, **kwargs)
        return BaseResponse(resp.url, resp.status_code, resp.headers, _resp=resp)
    except Exception as error:
        logger.exception(
            "HEAD request failed - url: {}, status: {}, header keys: {}, error: {}",
            redact_url(url),
            _response_status(error),
            _header_keys(kwargs),
            type(error).__name__,
        )
        raise
