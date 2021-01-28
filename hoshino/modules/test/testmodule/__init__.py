'''
Author: AkiraXie
Date: 2021-01-28 03:24:30
LastEditors: AkiraXie
LastEditTime: 2021-01-29 00:30:59
Description: 
Github: http://github.com/AkiraXie/
'''
from nonebot.adapters import Bot, Event
from hoshino.service import Service
sv = Service('test')
test = sv.on_command('test', aliases={'测试'})


@test.handle()
async def handle_test(bot: Bot):
    await test.finish('测试成功！')
