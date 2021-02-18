'''
Author: AkiraXie
Date: 2021-02-13 20:32:08
LastEditors: AkiraXie
LastEditTime: 2021-02-13 20:51:36
Description: 
Github: http://github.com/AkiraXie/
'''
from hoshino import Service, R, Bot, Event, Message
import random
import os
sv = Service('longwang', enable_on_default=False, visible=False)

lwang = sv.on_command('迫害龙王')


@lwang.handle()
async def _(bot: Bot, event: Event):
    gid = event.group_id
    dragon_king = await bot.get_group_honor_info(group_id=gid, type='talkative')
    dragon_king = dragon_king['current_talkative']['user_id']
    longwanglist = list()
    longwangmelist = list()
    for lw in os.listdir(R.img('longwang/').path):
        if lw.startswith('longwangme'):
            longwangmelist.append(lw)
        else:
            longwanglist.append(lw)
    longwangme = R.img('longwang/', random.choice(longwangmelist)).CQcode
    longwang = R.img('longwang/', random.choice(longwanglist)).CQcode
    if dragon_king == event.self_id:
        await lwang.finish(Message(f'{longwangme}'))
    await lwang.finish(Message(f'[CQ:at,qq={dragon_king}]\n{longwang}'))
