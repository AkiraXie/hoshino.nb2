"""Small network-related helpers."""

from collections.abc import Mapping
from typing import Any

from . import aiohttpx


async def get_redirect(
    url: str,
    headers: Mapping[str, Any] | None = None,
) -> str | None:
    response = await aiohttpx.get(
        url,
        follow_redirects=False,
        headers=headers or {},
        verify=True,
    )
    return response.headers.get("Location") or url


__all__ = ["get_redirect"]
