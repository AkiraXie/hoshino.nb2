'''
Author: AkiraXie
Date: 2021-01-28 02:03:18
LastEditors: AkiraXie
LastEditTime: 2021-01-28 21:00:17
Description: 
Github: http://github.com/AkiraXie/
'''
import nonebot
hsn_config = nonebot.get_driver().config



from nonebot.adapters.cqhttp import Bot
from .util import get_bot_list,sucmd
from .service import Service
from .event import Event