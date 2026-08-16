"""OneBot v11 运行时 patch — Bot.send() + 自定义事件注册"""

from __future__ import annotations

from typing import Any

from hoshino.platform.message import (
    UNKNOWN_USER_HEADER,
    UNKNOWN_USER_ID,
    call_header_from_names,
)
from hoshino.platform.ob11.types import Adapter, Bot, Event, Message, MessageSegment, escape


async def send(
    self: Bot,
    event: Event,
    message: str | Message | MessageSegment,
    at_sender: bool = False,
    call_header: bool = False,
    **kwargs,
) -> Any:
    """根据 ``event`` 向触发事件的主体发送消息。"""
    message = escape(message, escape_comma=False) if isinstance(message, str) else message
    msg = message if isinstance(message, Message) else Message(message)

    at_sender = at_sender and getattr(event, "user_id", None)

    params: dict[str, Any] = {}
    if getattr(event, "user_id", None):
        params["user_id"] = event.user_id
    if getattr(event, "group_id", None):
        params["group_id"] = event.group_id
    params.update(kwargs)

    if "message_type" not in params:
        if params.get("group_id"):
            params["message_type"] = "group"
        elif params.get("user_id"):
            params["message_type"] = "private"
        else:
            raise ValueError("Cannot guess message type to reply!")

    params["message"] = msg
    if params["message_type"] != "private":
        if at_sender:
            params["message"] = (
                MessageSegment.at(params["user_id"]) + MessageSegment.text(" ") + params["message"]
            )
        if call_header:
            if params["user_id"] == UNKNOWN_USER_ID:
                header = UNKNOWN_USER_HEADER
            else:
                info = await self.get_group_member_info(
                    group_id=event.group_id, user_id=event.user_id, no_cache=True
                )
                header = call_header_from_names(
                    escape(name, escape_comma=False)
                    for name in (info["title"], info["card"], info["nickname"])
                )
            params["message"] = header + params["message"]
        return await self.send_group_msg(
            group_id=params["group_id"],
            message=params["message"],
            auto_escape=params.get("auto_escape", False),
        )
    return await self.send_private_msg(
        user_id=params["user_id"],
        message=params["message"],
        auto_escape=params.get("auto_escape", False),
    )


def apply_patches() -> None:
    """应用 OB11 运行时 monkey-patch"""
    Adapter.custom_send(send)
