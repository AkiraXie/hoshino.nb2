'''
Author: AkiraXie
Date: 2021-02-11 23:05:08
LastEditors: AkiraXie
LastEditTime: 2021-02-11 23:49:02
Description: 
Github: http://github.com/AkiraXie/
'''
import base64
from hoshino import Service, Bot, Event
sv = Service('b64', enable_on_default=False)




@sv.on_command('b64加密',only_group=False)
async def _(bot: Bot, event: Event):
    res = base64.b64encode(event.get_plaintext().encode()).decode('utf8')
    await bot.send(event,res)





@sv.on_command('b64', aliases={'b64解密'},only_group=False)
async def _(bot: Bot, event: Event):
    res = base64.b64decode(event.get_plaintext()).decode('utf8')
    await bot.send(event,res)
