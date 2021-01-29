'''
Author: AkiraXie
Date: 2021-01-28 23:36:14
LastEditors: AkiraXie
LastEditTime: 2021-01-30 00:00:02
Description: 
Github: http://github.com/AkiraXie/
'''
from hoshino.matcher import on_metaevent
from hoshino.typing import T_State
from hoshino import Bot, hsn_config
from hoshino.event import LifecycleMetaEvent, Event


async def lifecycle(bot: Bot, event: Event, state: T_State) -> bool:
    return isinstance(event, LifecycleMetaEvent)

lisenlife = on_metaevent(rule=lifecycle)


@lisenlife.handle()
async def _(bot: Bot, event: LifecycleMetaEvent):
    if event.sub_type == 'connect':
        for su in hsn_config.superusers:
            await bot.send_private_msg(user_id=int(su), message='生命周期上线~')
