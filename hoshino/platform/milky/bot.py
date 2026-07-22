"""Milky bot wrappers returning the shapes used by Hoshino services."""

from __future__ import annotations

from typing import Any

from nonebot.compat import model_dump

from hoshino.platform.milky.types import Bot


async def get_media_download_headers(bot: Bot, url: str) -> dict[str, str]:
    return {}


async def get_media_url(bot: Bot, media) -> str | None:
    if url := getattr(media, "url", None):
        return str(url)
    data = getattr(media, "data", None)
    if isinstance(data, dict):
        for key in ("temp_url", "uri", "url"):
            if value := data.get(key):
                return str(value)
    return None


async def get_group_list(bot: Bot) -> list[dict[str, Any]]:
    return [model_dump(group) for group in await bot.get_group_list()]


async def get_group_member_info(
    bot: Bot,
    group_id: int | str,
    user_id: int | str,
    *,
    no_cache: bool = True,
) -> dict[str, Any]:
    member = await bot.get_group_member_info(
        group_id=int(group_id), user_id=int(user_id), no_cache=no_cache
    )
    return model_dump(member)


async def upload_group_file(
    bot: Bot,
    group_id: int | str,
    *,
    name: str,
    file: str,
):
    return await bot.upload_group_file(
        group_id=int(group_id), path=file, file_name=name
    )
