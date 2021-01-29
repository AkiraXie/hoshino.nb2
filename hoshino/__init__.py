'''
Author: AkiraXie
Date: 2021-01-28 02:03:18
LastEditors: AkiraXie
LastEditTime: 2021-01-29 18:09:14
Description: 
Github: http://github.com/AkiraXie/
'''
import nonebot
hsn_config = nonebot.get_driver().config


from .res import rhelper

'''
R本身是一个字符串，并重载了`.`,`+`,`()`运算符,但屏蔽了对字符串本身进行修改的操作。
    
并且对图片对象进行了取`CQcode`和`open()`的操作。
    
e.g：
    
`R.img.priconne`==`R.img('priconne')`==`R+'img'+'priconne'`
'''
R=rhelper()


from nonebot.adapters.cqhttp import Bot
from nonebot.adapters.cqhttp.message import Message
from .util import get_bot_list,sucmd
from .service import Service
from .event import Event