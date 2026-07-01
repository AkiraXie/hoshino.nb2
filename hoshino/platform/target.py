from __future__ import annotations

import json
from enum import Enum
from typing import Any

from nonebot.adapters import Bot, Event
from nonebot_plugin_alconna.uniseg import Target, get_target
from nonebot_plugin_alconna.uniseg.constraint import SerializeFailed
from .ob11.event import get_group_id, get_user_id


def group_target(group_id: int | str) -> Target:
    return Target.group(str(group_id))


def private_target(user_id: int | str) -> Target:
    return Target.user(str(user_id))


def target_from_event(bot: Bot, event: Event) -> Target:
    try:
        return get_target(event, bot)
    except SerializeFailed:
        group_id = get_group_id(event)
        if group_id is not None:
            return group_target(group_id)
        user_id = get_user_id(event)
        if user_id is not None:
            return private_target(user_id)
        raise


def platform_key(bot: Bot | None = None, adapter_name: str | None = None) -> str:
    name = adapter_name
    if name is None and bot is not None:
        name = bot.adapter.get_name()
    normalized = (name or "").strip().lower().replace(" ", "")
    if normalized in {"onebotv11", "onebot11", "ob11"}:
        return "ob11"
    return normalized or "unknown"


def group_scope_key(group_id: int | str, *, platform: str = "ob11") -> str:
    return f"{platform}:{group_id}"


def target_scope_key(target: Target, *, platform: str = "ob11") -> str:
    if target.private:
        return f"{platform}:private:{target.id}"
    if target.parent_id:
        return f"{platform}:{target.parent_id}:{target.id}"
    return group_scope_key(target.id, platform=platform)


def event_scope_key(bot: Bot, event: Event) -> str | None:
    group_id = get_group_id(event)
    if group_id is not None:
        return group_scope_key(group_id, platform=platform_key(bot))
    try:
        return target_scope_key(target_from_event(bot, event), platform=platform_key(bot))
    except SerializeFailed:
        return None


def dump_target(target: Target) -> str:
    return json.dumps(_jsonable(target.dump(save_self_id=False)), ensure_ascii=False)


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(item) for item in value]
    if isinstance(value, Enum):
        return value.value
    return value


def load_target(data: str | dict[str, Any]) -> Target:
    if isinstance(data, str):
        data = json.loads(data)
    return Target.load(dict(data))


def load_target_or_group(data: str | dict[str, Any] | None, group_id: int | str) -> Target:
    if data:
        try:
            return load_target(data)
        except (TypeError, ValueError, KeyError):
            pass
    return group_target(group_id)
