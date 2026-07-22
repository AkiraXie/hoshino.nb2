"""Cross-adapter forwarding of a message referenced by a reaction."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from nonebot.adapters import Bot
from nonebot_plugin_alconna.uniseg import Target

from hoshino.platform.message import send_forward_to_target
from hoshino.platform.models import ReactionInfo, RetrievedMessage
from hoshino.platform.telegram.types import Bot as TelegramBot


async def forward_reacted_message(
    bot: Bot,
    target: Target,
    reaction: ReactionInfo,
    message: RetrievedMessage | None = None,
) -> Sequence[Any]:
    """Forward a reaction source using the adapter's native capability.

    Telegram has a native cross-chat forward endpoint but cannot retrieve a
    message body by ID. OB11 and Milky receive a normalized message and build
    a local forward through the existing platform facade.
    """

    if isinstance(bot, TelegramBot):
        try:
            return [
                await bot.forward_message(
                    chat_id=target.id,
                    from_chat_id=reaction.group_id,
                    message_id=reaction.message_id,
                )
            ]
        except Exception:
            if message is None:
                raise

    if message is None:
        raise ValueError("A normalized message is required for local forwarding")
    return await send_forward_to_target(bot, target, message.messages)


__all__ = ["forward_reacted_message"]
