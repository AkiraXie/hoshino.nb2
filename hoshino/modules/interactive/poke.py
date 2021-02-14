'''
Author: AkiraXie
Date: 2021-02-06 21:22:43
LastEditors: AkiraXie
LastEditTime: 2021-02-15 01:42:03
Description: 
Github: http://github.com/AkiraXie/
'''
from hoshino import Service, Bot, Message
from nonebot.adapters.cqhttp.event import PokeNotifyEvent, GroupRecallNoticeEvent
sv = Service('poke and recall',enable_on_default=False)
poke = sv.on_notice(False)


@poke.handle()
async def _(bot: Bot, event: PokeNotifyEvent):
    if event.is_tome() and event.user_id != event.self_id:
        await poke.finish(Message(f'[CQ:poke,qq={event.user_id}]'))


@poke.handle()
async def _(bot: Bot, event: GroupRecallNoticeEvent):
    message_id = event.message_id
    gid=event.group_id
    uid=event.user_id
    oid=event.operator_id
    res=await bot.get_msg(message_id=message_id)
    msg=Message(res['message'])
    user_dic=await bot.get_group_member_info(group_id=gid,user_id=uid,no_cache=True)
    user_card=user_dic['card'] if user_dic['card'] else user_dic['nickname']
    if oid==uid:
        await poke.finish(f'{user_card}({uid})撤回了消息:\n'+msg)
    else:
        await poke.finish(f'管理员撤回了{user_card}({uid})的消息:\n'+msg)
    
    
