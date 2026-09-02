"""Platform-aware superuser identifiers and routing helpers."""

from __future__ import annotations

from collections.abc import Iterable

from nonebot.adapters import Bot


def adapter_superuser_prefix(bot: Bot) -> str:
    """Return the prefix used by NoneBot's built-in ``SUPERUSER`` rule."""

    return bot.adapter.get_name().split(maxsplit=1)[0].lower()


def superuser_key(bot: Bot, user_id: int | str) -> str:
    return f"{adapter_superuser_prefix(bot)}:{user_id}"


def is_superuser(
    bot: Bot,
    user_id: int | str,
    configured: Iterable[str] | None = None,
) -> bool:
    """Match configured superusers using NoneBot's platform-aware semantics."""

    values = configured if configured is not None else bot.config.superusers
    user_id_str = str(user_id)
    return superuser_key(bot, user_id_str) in values or user_id_str in values


def superuser_ids_for_bot(
    bot: Bot,
    configured: Iterable[str] | None = None,
) -> list[str]:
    """Return private-chat IDs that belong to this bot's adapter."""
    values = configured if configured is not None else bot.config.superusers
    prefix = f"{adapter_superuser_prefix(bot)}:"
    result: list[str] = []
    seen: set[str] = set()
    for raw_value in values:
        value = str(raw_value)
        user_id = value.removeprefix(prefix) if value.startswith(prefix) else value
        if ":" in value and not value.startswith(prefix):
            continue
        if user_id and user_id not in seen:
            seen.add(user_id)
            result.append(user_id)
    return result


__all__ = [
    "adapter_superuser_prefix",
    "is_superuser",
    "superuser_ids_for_bot",
    "superuser_key",
]
