"""OB11 bot API wrappers — get_group_list, send_group_forward, etc."""

from __future__ import annotations

from collections.abc import Sequence
from urllib.parse import urlparse

from nonebot.adapters import Bot

from hoshino.platform.ob11.types import Message, MessageSegment


async def get_media_download_headers(bot: Bot, url: str) -> dict[str, str]:
    domain = urlparse(url).hostname
    if not domain or not domain.endswith("vip.qq.com"):
        return {}
    response = await bot.get_cookies(domain="vip.qq.com")
    cookies = response.get("cookies") if isinstance(response, dict) else None
    return {"Cookie": str(cookies)} if cookies else {}


async def get_media_url(bot: Bot, media) -> str | None:
    if url := getattr(media, "url", None):
        return str(url)
    data = getattr(media, "data", None)
    if isinstance(data, dict):
        for key in ("url", "file", "temp_url", "uri"):
            if value := data.get(key):
                return str(value)
    return None


async def get_group_list(bot: Bot) -> list[dict]:
    return await bot.get_group_list()


async def get_group_member_info(
    bot: Bot,
    group_id: int | str,
    user_id: int | str,
    *,
    no_cache: bool = True,
) -> dict:
    return await bot.get_group_member_info(
        group_id=int(group_id),
        user_id=int(user_id),
        no_cache=no_cache,
    )


async def send_group_forward(
    bot: Bot,
    group_id: int | str,
    messages: Sequence[Message | MessageSegment | str],
):
    return await bot.call_api(
        "send_group_forward_msg",
        group_id=int(group_id),
        messages=messages,
    )


async def send_private_forward(
    bot: Bot,
    user_id: int | str,
    messages: Sequence[Message | MessageSegment | str],
):
    return await bot.call_api(
        "send_private_forward_msg",
        user_id=int(user_id),
        messages=messages,
    )


async def upload_group_file(
    bot: Bot,
    group_id: int | str,
    *,
    name: str,
    file: str,
):
    return await bot.call_api(
        "upload_group_file",
        group_id=int(group_id),
        name=name,
        file=file,
    )
