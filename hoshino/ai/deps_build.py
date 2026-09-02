"""依赖 alconna/uninfo 的 AgentDeps 构造入口。

仅由插件层（chat / zssm / task_commands）在 nonebot 插件加载后 import。
插件符号顶层 import；未加载时 ``require``，已导入则跳过。
"""

from __future__ import annotations

import contextlib
import sys

import nonebot
from nonebot.adapters import Bot, Event
from nonebot.plugin import get_plugin

from hoshino.platform.event import get_user_id
from hoshino.platform.superuser import is_superuser

from .config import AIConfig
from .deps import AgentDeps, PermissionSnapshot, Telemetry


def _ensure_plugin(name: str) -> None:
    """若插件尚未加载则 ``nonebot.require``；已加载/已导入则跳过。"""
    if get_plugin(name) is not None or name in sys.modules:
        return
    nonebot.require(name)


_ensure_plugin("nonebot_plugin_alconna")
_ensure_plugin("nonebot_plugin_uninfo")

from nonebot_plugin_uninfo import get_session  # noqa: E402

from hoshino.platform.target import event_scope_key, target_from_event  # noqa: E402


async def build_permission_snapshot(bot: Bot, event: Event) -> PermissionSnapshot:
    """从当前事件构造权限快照。uninfo 解析失败时退化为仅 SUPERUSER 判断。"""
    user_id = get_user_id(event)
    uid = str(user_id) if user_id is not None else None
    is_super = bool(uid is not None and is_superuser(bot, user_id))
    is_admin = is_super
    if uid is not None:
        with contextlib.suppress(Exception):
            session = await get_session(bot=bot, event=event)
            member = session.member if session is not None else None
            if member is not None:
                role_ids = {role.id for role in member.roles or []}
                if role_ids & {"ADMINISTRATOR", "OWNER"}:
                    is_admin = True
    return PermissionSnapshot(user_id=uid, is_superuser=is_super, is_admin=is_admin)


def construct_chat_deps(
    bot: Bot,
    event: Event,
    config: AIConfig,
    permissions: PermissionSnapshot,
    *,
    provider_id: str,
    model: str,
) -> AgentDeps:
    """构造即时聊天 surface 的 AgentDeps。"""
    scope_key = event_scope_key(bot, event)
    return AgentDeps(
        surface="chat",
        scope_key=scope_key,
        target=target_from_event(bot, event),
        config=config,
        permissions=permissions,
        bot=bot,
        event=event,
        telemetry=Telemetry(
            provider_id=provider_id,
            scope_key=scope_key or "",
            model=model,
        ),
    )
