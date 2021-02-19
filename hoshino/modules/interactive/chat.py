from typing import Dict
from loguru import logger
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


class reapter:
    def __init__(self, msg: str , repeated: bool , prob: float) -> None:
        self.msg = msg
        self.repeated = repeated
        self.prob = prob

    def check(self, current_msg: str) -> bool:
        return not self.repeated and current_msg == self.msg


# 想了想要复现HoshinoBot的复读还是得有个全局字典来存数据F
GROUP_STATE: Dict[int, reapter] = dict()


async def random_reapt(bot: Bot, event: Event):
    gid = event.group_id
    msg = event.raw_message
    if gid not in GROUP_STATE:
        GROUP_STATE[gid] = reapter(msg, False, 0.0)
        return
    current_reapter = GROUP_STATE[gid]
    if current_reapter.check(msg):
        if  p := current_reapter.prob > random.random():
            try:
                GROUP_STATE[gid] = reapter(msg, True, 0.0)
                await bot.send(event,Message(msg))
            except Exception as e:
                logger.exception(e)
        else:
            p = 1-(1-p) / 1.6
            GROUP_STATE[gid] = reapter(msg, False, p)
    else:
        GROUP_STATE[gid] = reapter(msg, False, 0.0)
# 优先级为0，为了避免被正常命令裁剪message
sv1.on_message(priority=0,block=False).handle()(random_reapt)