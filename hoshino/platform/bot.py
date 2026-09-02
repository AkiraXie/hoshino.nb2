"""Adapter-aware bot API wrappers."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from nonebot.adapters import Bot
from nonebot_plugin_alconna.uniseg.fallback import FallbackStrategy

from hoshino.platform.milky.bot import get_file_url as milky_get_file_url
from hoshino.platform.milky.bot import get_group_list as milky_get_group_list
from hoshino.platform.milky.bot import (
    get_group_member_info as milky_get_group_member_info,
)
from hoshino.platform.milky.bot import (
    get_media_download_headers as milky_get_media_download_headers,
)
from hoshino.platform.milky.bot import get_media_url as milky_get_media_url
from hoshino.platform.milky.bot import upload_group_file as milky_upload_group_file
from hoshino.platform.milky.types import Bot as MilkyBot
from hoshino.platform.ob11.bot import get_group_list as ob11_get_group_list
from hoshino.platform.ob11.bot import (
    get_group_member_info as ob11_get_group_member_info,
)
from hoshino.platform.ob11.bot import (
    get_media_download_headers as ob11_get_media_download_headers,
)
from hoshino.platform.ob11.bot import get_media_url as ob11_get_media_url
from hoshino.platform.ob11.bot import upload_group_file as ob11_upload_group_file
from hoshino.platform.telegram.bot import (
    get_group_list as telegram_get_group_list,
)
from hoshino.platform.telegram.bot import (
    get_group_member_info as telegram_get_group_member_info,
)
from hoshino.platform.telegram.bot import (
    get_media_download_headers as telegram_get_media_download_headers,
)
from hoshino.platform.telegram.bot import get_media_url as telegram_get_media_url
from hoshino.platform.telegram.bot import upload_chat_file
from hoshino.platform.telegram.types import Bot as TelegramBot


async def get_group_list(bot: Bot) -> list[dict[str, Any]]:
    if isinstance(bot, MilkyBot):
        return await milky_get_group_list(bot)
    if isinstance(bot, TelegramBot):
        return await telegram_get_group_list(bot)
    return await ob11_get_group_list(bot)


async def get_media_download_headers(bot: Bot, url: str) -> dict[str, str]:
    if isinstance(bot, MilkyBot):
        return await milky_get_media_download_headers(bot, url)
    if isinstance(bot, TelegramBot):
        return await telegram_get_media_download_headers(bot, url)
    return await ob11_get_media_download_headers(bot, url)


async def get_media_url(bot: Bot, media: Any) -> str | None:
    if isinstance(bot, MilkyBot):
        return await milky_get_media_url(bot, media)
    if isinstance(bot, TelegramBot):
        return await telegram_get_media_url(bot, media)
    return await ob11_get_media_url(bot, media)


async def get_file_url(bot: Bot, event, media: Any) -> str | None:
    """Resolve an adapter-native incoming file to a downloadable URL."""
    if isinstance(bot, MilkyBot):
        return await milky_get_file_url(bot, event, media)
    return await get_media_url(bot, media)


async def get_group_member_info(
    bot: Bot,
    group_id: int | str,
    user_id: int | str,
    *,
    no_cache: bool = True,
) -> dict[str, Any]:
    if isinstance(bot, MilkyBot):
        return await milky_get_group_member_info(
            bot,
            group_id,
            user_id,
            no_cache=no_cache,
        )
    if isinstance(bot, TelegramBot):
        return await telegram_get_group_member_info(
            bot,
            group_id,
            user_id,
            no_cache=no_cache,
        )
    return await ob11_get_group_member_info(
        bot,
        group_id,
        user_id,
        no_cache=no_cache,
    )


async def send_group_forward(
    bot: Bot,
    group_id: int | str,
    messages: Sequence[Any],
    *,
    user_id: int | str | None = None,
    nickname: str | None = None,
    fallback: bool | FallbackStrategy = FallbackStrategy.rollback,
    sequential_delay: float = 0.3,
) -> list[Any]:
    # Deferred import avoids the platform facade's bot -> message import order.
    from hoshino.platform.message import send_forward_to_target
    from hoshino.platform.target import group_target

    return await send_forward_to_target(
        bot,
        group_target(group_id),
        messages,
        user_id=user_id,
        nickname=nickname,
        fallback=fallback,
        sequential_delay=sequential_delay,
    )


async def send_private_forward(
    bot: Bot,
    user_id: int | str,
    messages: Sequence[Any],
    *,
    node_user_id: int | str | None = None,
    nickname: str | None = None,
    fallback: bool | FallbackStrategy = FallbackStrategy.rollback,
    sequential_delay: float = 0.3,
) -> list[Any]:
    # Deferred import avoids the platform facade's bot -> message import order.
    from hoshino.platform.message import send_forward_to_target
    from hoshino.platform.target import private_target

    return await send_forward_to_target(
        bot,
        private_target(user_id),
        messages,
        user_id=node_user_id,
        nickname=nickname,
        fallback=fallback,
        sequential_delay=sequential_delay,
    )


async def upload_group_file(
    bot: Bot,
    group_id: int | str,
    *,
    name: str,
    file: str,
):
    if isinstance(bot, MilkyBot):
        return await milky_upload_group_file(
            bot,
            group_id,
            name=name,
            file=file,
        )
    if isinstance(bot, TelegramBot):
        return await upload_chat_file(bot, group_id, name=name, file=file)
    return await ob11_upload_group_file(bot, group_id, name=name, file=file)
