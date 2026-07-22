"""Forward reacted messages to the reacting superuser's private chat."""

from __future__ import annotations

from nonebot.adapters import Bot
from nonebot.rule import Rule

from hoshino.core.permission import SUPERUSER
from hoshino.platform import (
    ReactedMessage,
    Reaction,
    ReactionInfo,
    RetrievedMessage,
    forward_reacted_message,
    platform_key,
    private_target,
    reaction_event_rule,
)

from .sv import sv
from .runtime import runtime, store


async def added_reaction(
    reaction: ReactionInfo | None = Reaction(),
) -> bool:
    return reaction is not None and reaction.is_add


x_reaction = sv.on_notice(
    rule=reaction_event_rule & Rule(added_reaction),
    permission=SUPERUSER,
    priority=5,
    block=True,
)


@x_reaction.handle()
async def handle_x_reaction(
    bot: Bot,
    reaction: ReactionInfo | None = Reaction(),
    reacted_message: RetrievedMessage | None = ReactedMessage(additions_only=True),
) -> None:
    if reaction is None or not reaction.is_add:
        return
    platform = platform_key(bot)
    if platform != "telegram":
        claimed = await store.claim_reaction(
            platform, reaction.group_id, reaction.message_id, reaction.user_id
        )
        if not claimed:
            return
    try:
        await forward_reacted_message(
            bot,
            private_target(reaction.user_id),
            reaction,
            reacted_message,
        )
    except Exception as exc:
        sv.logger.error(
            f"X reaction forwarding failed on {platform} for user "
            f"{reaction.user_id}: {type(exc).__name__}. For Telegram, the user "
            "must start the bot before it can send a private message.",
            exception=False,
        )
        await runtime.errors.enqueue(f"reaction-user-{reaction.user_id}", exc)


__all__ = ["added_reaction", "handle_x_reaction", "x_reaction"]
