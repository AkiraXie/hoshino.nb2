'''
Author: AkiraXie
Date: 2021-01-27 23:37:56
LastEditors: AkiraXie
LastEditTime: 2021-01-28 00:14:40
Description: 
Github: http://github.com/AkiraXie/
'''
from nonebot import on_command
from nonebot.rule import to_me
from nonebot.typing import T_State
from nonebot.adapters import Bot, Event
from nonebot.adapters.cqhttp.message import Message
zai = on_command('zai', aliases={'在?', '在？', '在吗', '在么？', '在嘛', '在嘛？'},
                 rule=to_me(), block=True)


@zai.handle()
async def handle_zai(bot: Bot):
    await zai.finish(Message('布丁~布丁~'))
