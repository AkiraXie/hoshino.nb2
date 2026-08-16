"""写接口与媒体代理的可选共享密钥鉴权。

- 写接口（收藏/标签/黑名单/删除帖子）：配置 ``IMAGE_WEB_WRITE_TOKEN`` 后要求
  ``X-Image-Web-Write-Token`` 头或 ``token`` 查询参数一致；未配置时放行
  （开箱即用，适用于本地/未暴露部署，如需加固请配置密钥）。
- 媒体代理（``/media/proxy``）：配置 ``IMAGE_WEB_PROXY_TOKEN`` 后要求携带 token；
  未配置时放行任意公网域名（SSRF 私网地址拒绝始终生效，见 ``image_web/x/server.py``）。

token 比较使用 ``secrets.compare_digest``，避免时序侧信道泄露。
"""

import os
import secrets

from fastapi import HTTPException, Request

# 以下均为环境变量/header/参数的名字符串常量，非硬编码密码。
WRITE_TOKEN_ENV = "IMAGE_WEB_WRITE_TOKEN"  # noqa: S105
PROXY_TOKEN_ENV = "IMAGE_WEB_PROXY_TOKEN"  # noqa: S105
WRITE_TOKEN_HEADER = "X-Image-Web-Write-Token"  # noqa: S105
PROXY_TOKEN_HEADER = "X-Image-Web-Proxy-Token"  # noqa: S105
TOKEN_QUERY_PARAM = "token"  # noqa: S105


def _read_token(env_name: str) -> str | None:
    value = os.environ.get(env_name, "")
    return value if value else None


def write_token() -> str | None:
    """写接口共享密钥；未配置返回 None（此时写操作放行）。"""
    return _read_token(WRITE_TOKEN_ENV)


def proxy_token() -> str | None:
    """媒体代理共享密钥；未配置返回 None（此时放行任意公网域名）。"""
    return _read_token(PROXY_TOKEN_ENV)


def _token_matches(supplied: str | None, expected: str) -> bool:
    return bool(supplied) and secrets.compare_digest(supplied, expected)


def require_write_token(request: Request) -> None:
    """FastAPI 依赖：写接口鉴权。

    未配置 ``IMAGE_WEB_WRITE_TOKEN`` 时放行（开箱即用）；配置后要求携带一致
    token，否则 401。
    """
    expected = write_token()
    if expected is None:
        return
    supplied = request.headers.get(WRITE_TOKEN_HEADER) or request.query_params.get(
        TOKEN_QUERY_PARAM
    )
    if not _token_matches(supplied, expected):
        raise HTTPException(401, "Invalid or missing write token")


def require_proxy_token(request: Request) -> None:
    """FastAPI 依赖：媒体代理鉴权。

    未配置 ``IMAGE_WEB_PROXY_TOKEN`` 时放行任意公网域名（SSRF 私网拒绝由
    ``image_web/x/server.py`` 负责）；配置后要求携带一致 token，否则 401。
    """
    expected = proxy_token()
    if expected is None:
        return
    supplied = request.headers.get(PROXY_TOKEN_HEADER) or request.query_params.get(
        TOKEN_QUERY_PARAM
    )
    if not _token_matches(supplied, expected):
        raise HTTPException(401, "Invalid or missing proxy token")
