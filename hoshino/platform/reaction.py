"""Adapter-neutral reaction dependency injection.

Business handlers receive :class:`ReactionInfo` and :class:`RetrievedMessage`
instead of importing OB11 or Milky event models or calling adapter APIs.
"""

from __future__ import annotations

from nonebot.adapters import Bot, Event
from nonebot.params import Depends
from nonebot.rule import Rule

from hoshino.platform.milky import reaction as milky_reaction
from hoshino.platform.milky.types import Bot as MilkyBot
from hoshino.platform.milky.types import Event as MilkyEvent
from hoshino.platform.models import ReactionInfo, RetrievedMessage
from hoshino.platform.ob11 import reaction as ob11_reaction
from hoshino.platform.ob11.types import Bot as OB11Bot
from hoshino.platform.telegram import reaction as telegram_reaction
from hoshino.platform.telegram.types import Bot as TelegramBot
from hoshino.platform.telegram.types import MessageReactionEvent


def get_reaction_info(event: Event) -> ReactionInfo | None:
    """Return normalized metadata for supported reaction events."""

    if isinstance(event, MilkyEvent):
        return milky_reaction.get_reaction_info(event)
    if isinstance(event, MessageReactionEvent):
        return telegram_reaction.get_reaction_info(event)
    return ob11_reaction.get_reaction_info(event)


async def is_reaction_event(event: Event) -> bool:
    """NoneBot rule checker shared by all reaction consumers."""

    return get_reaction_info(event) is not None


reaction_event_rule = Rule(is_reaction_event)


async def _reaction_dependency(event: Event) -> ReactionInfo | None:
    return get_reaction_info(event)


def Reaction() -> ReactionInfo | None:
    """Inject normalized reaction metadata into a matcher rule or handler."""

    return Depends(_reaction_dependency)


async def _get_reacted_message(
    bot: Bot,
    reaction: ReactionInfo,
) -> RetrievedMessage | None:
    if isinstance(bot, MilkyBot):
        return await milky_reaction.get_reacted_message(bot, reaction)
    if isinstance(bot, OB11Bot):
        return await ob11_reaction.get_reacted_message(bot, reaction)
    if isinstance(bot, TelegramBot):
        # Telegram reaction updates contain no message body and Bot API has
        # no get-message endpoint. Consumers needing forwarding use the
        # native forward facade with ReactionInfo instead.
        return None
    return None


def ReactedMessage(
    *face_ids: str,
    additions_only: bool = False,
) -> RetrievedMessage | None:
    """Inject the message referenced by a matching reaction.

    Optional filters are applied before any adapter API call.  This keeps
    unrelated reaction matchers from fetching the same source message.
    """

    async def _dependency(bot: Bot, event: Event) -> RetrievedMessage | None:
        reaction = get_reaction_info(event)
        if reaction is None:
            return None
        if face_ids and reaction.face_id not in face_ids:
            return None
        if additions_only and not reaction.is_add:
            return None
        return await _get_reacted_message(bot, reaction)

    return Depends(_dependency)


__all__ = [
    "ReactedMessage",
    "Reaction",
    "ReactionInfo",
    "RetrievedMessage",
    "get_reaction_info",
    "is_reaction_event",
    "reaction_event_rule",
]
