'''
Author: AkiraXie
Date: 2021-01-28 02:03:18
LastEditors: AkiraXie
LastEditTime: 2021-06-12 03:41:42
Description: 
Github: http://github.com/AkiraXie/
'''
import nonebot
import os


hsn_config = nonebot.get_driver().config
db_dir=os.path.join(hsn_config.data,'db/')
service_dir=os.path.join(hsn_config.data,'service/')
os.makedirs(db_dir,exist_ok=True)
os.makedirs(service_dir,exist_ok=True)

from .typing import Final,Any,Union
from .res import RHelper
from nonebot.adapters.cqhttp import Bot
from nonebot.adapters.cqhttp.utils import escape
from .message import MessageSegment, Message, MessageBuilder
from .event import Event


async def send(self:Bot, event: Event,
                   message: Union[str, Message, MessageSegment],
                   at_sender: bool = False,
                   call_header:bool = False,
                   **kwargs) -> Any:
    """
        :说明:

        改自 ``cqhttp.bot.send``

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
    message = escape(message, escape_comma=False) if isinstance(
    message, str) else message
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
            params["message"] = MessageSegment.at(params["user_id"]) + \
            MessageSegment.text(" ") + params["message"]
        if call_header:
            if params["user_id"] == 80000000:
                header = '>???\n'
            else:
                info = await self.get_group_member_info(
                    group_id=event.group_id,
                    user_id=event.user_id,
                    no_cache=True
                )
                for i in (info['title'], info['card'], info['nickname']):
                    if i:
                        header = f'>{escape(i)}\n'
                        break
            params["message"]=header+params["message"]
            
    return await self.send_msg(**params)

Bot.send=send


'''
`R`本身是一个字符串，并重载了`.`,`+`,`()`等运算符,但屏蔽了对字符串本身进行修改的一些操作。

**请不要对`R`进行赋值操作！**

并且对图片对象进行了取`CQcode`和`open()`的操作。
    
e.g：
    
`R.img.priconne`==`R.img('priconne')`==`R+'img'+'priconne'`
'''
R: Final[RHelper] = RHelper()



from .schedule import scheduled_job, add_job
from .typing import T_State
from .service import Service
from .util import aiohttpx, get_bot_list, sucmd, sucmds