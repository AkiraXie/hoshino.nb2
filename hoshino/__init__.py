"""
Author: AkiraXie
Date: 2021-01-28 02:03:18
LastEditors: AkiraXie
LastEditTime: 2022-02-17 00:50:55
Description: 
Github: http://github.com/AkiraXie/
"""
import nonebot
import os

driver = nonebot.get_driver()
hsn_config = driver.config
fav_dir = os.path.join(hsn_config.data, "favorite/")
img_dir = os.path.join(hsn_config.data, "image/")
db_dir = os.path.join(hsn_config.data, "db/")
service_dir = os.path.join(hsn_config.data, "service/")
os.makedirs(fav_dir, exist_ok=True)
os.makedirs(img_dir, exist_ok=True)
os.makedirs(db_dir, exist_ok=True)
os.makedirs(service_dir, exist_ok=True)

from .typing import Final, Any, Union, T_ArgsParser, T_Handler, Optional, Type
from .res import RHelper
from nonebot.adapters.onebot.v11 import Bot
from nonebot.adapters.onebot.v11.utils import escape
from nonebot.params import Depends
from nonebot.matcher import Matcher, current_bot
from .message import MessageSegment, Message, MessageTemplate
from .event import Event

# patch bot.send

async def send(
    self: Bot,
    event: Event,
    message: Union[str, Message, MessageSegment],
    at_sender: bool = False,
    call_header: bool = False,
    **kwargs,
) -> Any:
    """
    :说明:

    改自 ``onebot.v11.bot.send``

    根据 ``event``  向触发事件的主体发送消息。

    :参数:

    * ``event: Event``: Event 对象
    * ``message: Union[str, Message, MessageSegment]``: 要发送的消息
    * ``at_sender: bool``: 是否 @ 事件主体
    * ``call_header: bool``: 是否添加事件主体信息
    * ``**kwargs``: 覆盖默认参数

    :返回:

    - ``Any``: API 调用返回数据

    :异常:

    - ``ValueError``: 缺少 ``user_id``, ``group_id``
    - ``NetworkError``: 网络错误
    - ``ActionFailed``: API 调用失败
    """
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
                    group_id=event.group_id, user_id=event.user_id
                )
                for i in (info["title"], info["card"], info["nickname"]):
                    if i:
                        header = f">{escape(i,escape_comma=False)}\n"
                        break
            params["message"] = header + params["message"]

    return await self.send_msg(**params)


Bot.send = send

# patch matcher.got


@classmethod
def got(
    cls: Type[Matcher],
    key: str,
    prompt: Optional[Union[str, Message, MessageSegment, MessageTemplate]] = None,
    args_parser: Optional[T_ArgsParser] = None,
    parameterless: Optional[list] = None,
):
    """改自 `nonebot.Matcher.got`

    装饰一个函数来指示 NoneBot 获取一个参数 `key`

    当要获取的 `key` 不存在时接收用户新的一条消息再运行该函数，如果 `key` 已存在则直接继续运行

    参数:
        key: 参数名
        prompt: 在参数不存在时向用户发送的消息
        args_parser: 参数解析器
        parameterless: 非参数类型依赖列表
    """

    async def _key_getter(event: Event, matcher: "Matcher"):
        matcher.set_target(key)
        if matcher.get_target() == key:
            if not args_parser:
                matcher.set_arg(key, event.get_plaintext())
            else:
                bot: Bot = current_bot.get()
                await args_parser(bot, event, matcher.state)
            return
        if matcher.get_arg(key, ...) is not ...:
            return
        await matcher.reject(prompt)

    _parameterless = [
        Depends(_key_getter),
        *(parameterless or []),
    ]

    def _decorator(func: T_Handler) -> T_Handler:

        if cls.handlers and cls.handlers[-1].call is func:
            func_handler = cls.handlers[-1]
            for depend in reversed(_parameterless):
                func_handler.prepend_parameterless(depend)
        else:
            cls.append_handler(func, parameterless=_parameterless)

        return func

    return _decorator


Matcher.got = got

"""
`R`本身是一个字符串，并重载了`.`,`+`,`()`等运算符,但屏蔽了对字符串本身进行修改的一些操作。

**请不要对`R`进行赋值操作！**

并且对图片对象进行了取`CQcode`和`open()`的操作。
    
e.g：
    
`R.img.priconne`==`R.img('priconne')`==`R+'img'+'priconne'`
"""
R: Final[RHelper] = RHelper()

from .permission import SUPERUSER
from .schedule import scheduled_job, add_job
from .typing import T_State
from .service import Service
from .util import aiohttpx, get_bot_list, sucmd, sucmds
