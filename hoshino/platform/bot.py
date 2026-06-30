from __future__ import annotations

from collections.abc import Sequence

from nonebot.adapters import Bot

from hoshino.message import Message, MessageSegment


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
