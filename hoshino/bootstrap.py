"""Hoshino 运行时初始化。必须在 nonebot.init() 后、nonebot.run() 前调用。"""
from __future__ import annotations
from typing import Any

import nonebot
from hoshino.platform.ob11.types import Adapter, Bot
from hoshino.platform.ob11.types import escape

from hoshino.platform.ob11.types import MessageSegment, Message
from hoshino.platform.ob11.events import GroupReactionEvent, GroupMsgEmojiLikeEvent
from hoshino.platform.ob11.types import Event
from . import config as _config
from . import hooks


# ── Bot.send patch ──

async def send(
    self: Bot,
    event: Event,
    message: str | Message | MessageSegment,
    at_sender: bool = False,
    call_header: bool = False,
    **kwargs,
) -> Any:
    """根据 ``event`` 向触发事件的主体发送消息。"""
    message = (
        escape(message, escape_comma=False) if isinstance(message, str) else message
    )
    msg = message if isinstance(message, Message) else Message(message)

    at_sender = at_sender and getattr(event, "user_id", None)

    params = {}
    if getattr(event, "user_id", None):
        params["user_id"] = getattr(event, "user_id")
    if getattr(event, "group_id", None):
        params["group_id"] = getattr(event, "group_id")
    params.update(kwargs)

    if "message_type" not in params:
        if params.get("group_id", None):
            params["message_type"] = "group"
        elif params.get("user_id", None):
            params["message_type"] = "private"
        else:
            raise ValueError("Cannot guess message type to reply!")

    params["message"] = msg
    if params["message_type"] != "private":
        if at_sender:
            params["message"] = (
                MessageSegment.at(params["user_id"])
                + MessageSegment.text(" ")
                + params["message"]
            )
        if call_header:
            if params["user_id"] == 80000000:
                header = ">???\n"
            else:
                info = await self.get_group_member_info(
                    group_id=event.group_id, user_id=event.user_id, no_cache=True
                )
                for i in (info["title"], info["card"], info["nickname"]):
                    if i:
                        header = f">{escape(i, escape_comma=False)}\n"
                        break
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


# ── bootstrap ──

def bootstrap() -> None:
    driver = nonebot.get_driver()

    # 1. 创建数据目录
    _config.data_dir.mkdir(exist_ok=True)
    _config.static_dir.mkdir(exist_ok=True)
    data_dir = _config.data_dir
    for sub in ("favorite", "image", "db", "service", "video"):
        (data_dir / sub).mkdir(exist_ok=True)

    # 2. Patch Adapter
    Adapter.custom_send(send)

    # 3. 注册自定义事件模型
    Adapter.add_custom_model(GroupReactionEvent)
    Adapter.add_custom_model(GroupMsgEmojiLikeEvent)

    # 4. 配置日志
    # Lazy import: hoshino.log imports hoshino.service state used by bootstrap patches.
    from hoshino.core.log import configure as _log_configure
    _log_configure()

    # 5. 下发所有延迟 hook 到真实 driver
    hooks.replay(driver)
