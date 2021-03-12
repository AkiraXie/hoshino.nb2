'''
Author: AkiraXie
Date: 2021-01-28 02:03:18
LastEditors: AkiraXie
LastEditTime: 2021-03-12 04:33:19
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


from .typing import Final
from .res import rhelper


'''
`R`本身是一个字符串，并重载了`.`,`+`,`()`等运算符,但屏蔽了对字符串本身进行修改的一些操作。

**请不要对`R`进行赋值操作！**

并且对图片对象进行了取`CQcode`和`open()`的操作。
    
e.g：
    
`R.img.priconne`==`R.img('priconne')`==`R+'img'+'priconne'`
'''
R: Final[rhelper] = rhelper()


from nonebot.adapters.cqhttp import Bot
from .message import MessageSegment, Message
from .event import Event
from .schedule import scheduled_job, add_job
from .typing import T_State
from .service import Service
from .util import aiohttpx, get_bot_list, sucmd, sucmds