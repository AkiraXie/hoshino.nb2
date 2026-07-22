"""Runtime compatibility patches for the pinned Telegram adapter."""

from __future__ import annotations

from typing import Any

from nonebot.adapters.telegram import Bot, Event
from nonebot.adapters.telegram.model import Update

from hoshino.platform.telegram.events import MessageReactionEvent


_ALLOWED_UPDATES = [
    "message",
    "edited_message",
    "channel_post",
    "edited_channel_post",
    "inline_query",
    "chosen_inline_result",
    "callback_query",
    "shipping_query",
    "pre_checkout_query",
    "poll",
    "poll_answer",
    "my_chat_member",
    "chat_member",
    "chat_join_request",
    "message_reaction",
]


def apply_patches() -> None:
    """Parse reaction updates and request them from polling/webhook APIs."""

    if getattr(Event, "_hoshino_reaction_patch", False):
        return

    original_parse = getattr(Event, "_Event__parse_event").__func__

    def parse_event(cls: type[Event], payload: dict[str, Any]) -> Event:
        if "message_reaction" in payload:
            event = MessageReactionEvent.parse_event(payload["message_reaction"])
            event.telegram_model = Update.model_validate(payload)
            return event
        return original_parse(cls, payload)

    Event._Event__parse_event = classmethod(parse_event)
    original_call_api = Bot.call_api

    async def call_api(self: Bot, api: str, *args: Any, **kwargs: Any) -> Any:
        if (
            api in {"get_updates", "set_webhook"}
            and kwargs.get("allowed_updates") is None
        ):
            kwargs["allowed_updates"] = list(_ALLOWED_UPDATES)
        return await original_call_api(self, api, *args, **kwargs)

    Bot.call_api = call_api
    Event._hoshino_reaction_patch = True


__all__ = ["apply_patches"]
