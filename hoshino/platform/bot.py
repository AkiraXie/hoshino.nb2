"""Adapter-aware bot API wrappers."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from nonebot.adapters import Bot

from hoshino.platform.milky.bot import get_group_list as milky_get_group_list
from hoshino.platform.milky.bot import (
    get_group_member_info as milky_get_group_member_info,
)
from hoshino.platform.milky.bot import upload_group_file as milky_upload_group_file
from hoshino.platform.milky.types import Bot as MilkyBot
from hoshino.platform.ob11.bot import get_group_list as ob11_get_group_list
from hoshino.platform.ob11.bot import (
    get_group_member_info as ob11_get_group_member_info,
)
from hoshino.platform.ob11.bot import send_group_forward as ob11_send_group_forward
from hoshino.platform.ob11.bot import send_private_forward as ob11_send_private_forward
from hoshino.platform.ob11.bot import upload_group_file as ob11_upload_group_file
from hoshino.platform.telegram.bot import (
    get_group_list as telegram_get_group_list,
)
from hoshino.platform.telegram.bot import (
    get_group_member_info as telegram_get_group_member_info,
)
from hoshino.platform.telegram.bot import upload_chat_file
from hoshino.platform.telegram.types import Bot as TelegramBot


async def get_group_list(bot: Bot) -> list[dict[str, Any]]:
    if isinstance(bot, MilkyBot):
        return await milky_get_group_list(bot)
    if isinstance(bot, TelegramBot):
        return await telegram_get_group_list(bot)
    return await ob11_get_group_list(bot)


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
):
    if isinstance(bot, MilkyBot):
        raise NotImplementedError(
            "Milky forward nodes must be sent as a UniMessage reference"
        )
    if isinstance(bot, TelegramBot):
        raise NotImplementedError("Telegram cannot send constructed forward nodes")
    return await ob11_send_group_forward(bot, group_id, messages)


async def send_private_forward(
    bot: Bot,
    user_id: int | str,
    messages: Sequence[Any],
):
    if isinstance(bot, MilkyBot):
        raise NotImplementedError(
            "Milky forward nodes must be sent as a UniMessage reference"
        )
    if isinstance(bot, TelegramBot):
        raise NotImplementedError("Telegram cannot send constructed forward nodes")
    return await ob11_send_private_forward(bot, user_id, messages)


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
