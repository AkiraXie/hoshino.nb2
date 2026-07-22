"""Telegram bot API wrappers."""

from __future__ import annotations

from typing import Any
from urllib.parse import urljoin

from hoshino.platform.telegram.types import Bot, Message, MessageSegment


async def get_media_download_headers(bot: Bot, url: str) -> dict[str, str]:
    return {}


async def get_media_url(bot: Bot, media) -> str | None:
    if url := getattr(media, "url", None):
        return str(url)
    file_id = getattr(media, "id", None)
    if file_id is None:
        data = getattr(media, "data", None)
        file_id = data.get("file") if isinstance(data, dict) else None
    if not file_id:
        return None
    file = await bot.get_file(file_id=str(file_id))
    if not file.file_path:
        return None
    base_url = f"{bot.bot_config.api_server.rstrip('/')}/"
    return urljoin(base_url, f"file/bot{bot.bot_config.token}/{file.file_path}")


async def get_group_list(bot: Bot) -> list[dict[str, Any]]:
    """Telegram Bot API cannot enumerate every chat the bot has joined."""

    return []


async def get_chat(bot: Bot, chat_id: int | str) -> dict[str, Any]:
    chat = await bot.get_chat(chat_id=chat_id)
    return chat.model_dump(exclude_none=True)


async def get_group_member_info(
    bot: Bot,
    group_id: int | str,
    user_id: int | str,
    *,
    no_cache: bool = True,
) -> dict[str, Any]:
    del no_cache
    member = await bot.get_chat_member(chat_id=group_id, user_id=int(user_id))
    data = member.model_dump(exclude_none=True)
    user = member.user
    name = " ".join(part for part in (user.first_name, user.last_name) if part)
    data.update(
        {
            "card": "",
            "nickname": name or user.username or str(user.id),
            "user_id": user.id,
        }
    )
    return data


async def get_chat_member_status(
    bot: Bot,
    chat_id: int | str,
    user_id: int | str,
) -> str:
    member = await bot.get_chat_member(chat_id=chat_id, user_id=int(user_id))
    return str(member.status)


async def send_message(
    bot: Bot,
    chat_id: int | str,
    message: str | Message | MessageSegment,
    **kwargs: Any,
):
    return await bot.send_to(chat_id, message, **kwargs)


async def upload_chat_file(
    bot: Bot,
    chat_id: int | str,
    *,
    name: str,
    file: str,
):
    return await bot.send_document(chat_id=chat_id, document=file, caption=name)
