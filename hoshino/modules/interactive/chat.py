'''
Author: AkiraXie
Date: 2021-02-19 02:22:27
LastEditors: AkiraXie
LastEditTime: 2021-03-30 03:53:13
Description: 
Github: http://github.com/AkiraXie/
'''
from typing import Dict
from hoshino import Service, Bot, Event, Message
import random
sv = Service('chat', visible=False)


async def nihaole(bot: Bot, event: Event):
    await bot.send(event, '不许好,憋回去！')
sv.on_command('我好了').handle()(nihaole)


async def ddhaole(bot: Bot, event: Event):
    await bot.send(event, '那个朋友是不是你弟弟？')
sv.on_command('我有个朋友说他好了', aliases=('我朋友说他好了', )).handle()(ddhaole)


sv1 = Service('repeat', visible=False)


class repeater:
    def __init__(self, msg: str , repeated: bool , prob: float) -> None:
        self.msg = msg
        self.repeated = repeated
        self.prob = prob

    def check(self, current_msg: str) -> bool:
        return current_msg == self.msg


# 想了想要复现HoshinoBot的复读还是得有个全局字典来存数据
GROUP_STATE: Dict[int, repeater] = dict()

@sv1.on_message(block=False)
async def random_repeat(bot: Bot, event: Event):
    gid = event.group_id
    msg = event.raw_message
    if gid not in GROUP_STATE:
        GROUP_STATE[gid] =  repeater(msg, False, 0.0)
        return
    current_repeater = GROUP_STATE[gid]
    if current_repeater.check(msg):
        if current_repeater.repeated:
            return
        if  p :=current_repeater.prob > random.random():
            GROUP_STATE[gid] =  repeater(msg, True, 0.0)
            await bot.send(event,Message(msg))
        else:
            p = 1-(1-p) / 1.6
            GROUP_STATE[gid] =  repeater(msg, False, p)
    else:
        GROUP_STATE[gid] =  repeater(msg, False, 0.0)