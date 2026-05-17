"""Hoshino 运行时初始化。必须在 nonebot.init() 后、nonebot.run() 前调用。"""
from __future__ import annotations
from typing import Any, Union, Optional, Type

import nonebot
from nonebot.adapters.onebot.v11 import Adapter, Bot
from nonebot.adapters.onebot.v11.utils import escape
from nonebot.params import (
    Depends, BotParam, EventParam, StateParam, MatcherParam, DependParam,
)
from nonebot.dependencies import Dependent
from nonebot.matcher import Matcher, current_bot, current_event
from nonebot.typing import T_Handler

from .message import MessageSegment, Message, MessageTemplate
from .event import Event, GroupReactionEvent, GroupMsgEmojiLikeEvent
from . import config as _config
from . import hooks


# ── Bot.send patch（原 hoshino/__init__.py L40-124）──

async def send(
    self: Bot,
    event: Event,
    message: Union[str, Message, MessageSegment],
    at_sender: bool = False,
    call_header: bool = False,
    **kwargs,
) -> Any:
    """改自 ``onebot.v11.bot.send``，根据 ``event`` 向触发事件的主体发送消息。"""
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


# ── Matcher.got patch（原 hoshino/__init__.py L131-191）──

@classmethod
def got(
    cls: Type[Matcher],
    key: str,
    prompt: Optional[Union[str, Message, MessageSegment, MessageTemplate]] = None,
    parameterless: Optional[list] = None,
    args_parser: Optional[T_Handler] = None,
):
    """改自 ``nonebot.Matcher.got``。

    装饰一个函数来指示 NoneBot 获取一个参数 ``key``。
    当要获取的 ``key`` 不存在时接收用户新的一条消息再运行该函数，
    如果 ``key`` 已存在则直接继续运行。
    """
    if args_parser:
        args_parser = Dependent[Any].parse(
            call=args_parser,
            allow_types=[BotParam, EventParam, StateParam, MatcherParam, DependParam],
        )

    async def _key_getter(event: Event, matcher: "Matcher"):
        matcher.set_target(key)
        if matcher.get_target() == key:
            if not args_parser:
                matcher.set_arg(key, event.get_message())
            else:
                bot = current_bot.get()
                await args_parser(
                    matcher=matcher, bot=bot, event=event, state=matcher.state
                )
            return
        if matcher.get_arg(key, ...) is not ...:
            return
        await matcher.reject(prompt)

    _parameterless = (Depends(_key_getter), *(parameterless or ()))

    def _decorator(func: T_Handler) -> T_Handler:
        if cls.handlers and cls.handlers[-1].call is func:
            func_handler = cls.handlers[-1]
            new_handler = Dependent(
                call=func_handler.call,
                params=func_handler.params,
                parameterless=Dependent.parse_parameterless(
                    tuple(_parameterless), cls.HANDLER_PARAM_TYPES
                )
                + func_handler.parameterless,
            )
            cls.handlers[-1] = new_handler
        else:
            cls.append_handler(func, parameterless=_parameterless)

        return func

    return _decorator


# ── bootstrap ──

def bootstrap() -> None:
    driver = nonebot.get_driver()

    # 1. 创建数据目录
    _config.data_dir.mkdir(exist_ok=True)
    _config.static_dir.mkdir(exist_ok=True)
    data_dir = _config.data_dir
    for sub in ("favorite", "image", "db", "service", "video"):
        (data_dir / sub).mkdir(exist_ok=True)

    # 2. Patch Adapter 和 Matcher
    Adapter.custom_send(send)
    setattr(Matcher, "got", got)

    # 3. 注册自定义事件模型
    Adapter.add_custom_model(GroupReactionEvent)
    Adapter.add_custom_model(GroupMsgEmojiLikeEvent)

    # 4. 配置日志
    from .log import configure as _log_configure
    _log_configure()

    # 5. 下发所有延迟 hook 到真实 driver
    hooks.replay(driver)
