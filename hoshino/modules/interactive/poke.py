'''
Author: AkiraXie
Date: 2021-02-06 21:22:43
LastEditors: AkiraXie
LastEditTime: 2021-02-15 21:00:42
Description: 
Github: http://github.com/AkiraXie/
'''
from nonebot import on_notice
from hoshino import Service, Bot, Message
from nonebot.adapters.onebot.v11.event import PokeNotifyEvent, GroupRecallNoticeEvent

from hoshino.util import send_to_superuser
sv = Service('recall',enable_on_default=False)
poke = sv.on_notice()
recall = on_notice()


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
    
    
@recall.handle()
async def _(bot: Bot, event: GroupRecallNoticeEvent):
    message_id = event.message_id
    gid=event.group_id
    uid=event.user_id
    oid=event.operator_id
    res=await bot.get_msg(message_id=message_id)
    msg=Message(res['message'])
    user_dic=await bot.get_group_member_info(group_id=gid,user_id=uid,no_cache=True)
    user_card=user_dic['card'] if user_dic['card'] else user_dic['nickname']
    group_dic = await bot.get_group_info(group_id=gid, no_cache=True)
    gname = group_dic['group_name']
    if oid==uid:
        await send_to_superuser(bot,f'群名:{gname} 群号:{gid}\n{user_card}({uid})撤回了消息:\n'+msg)
    else:
        await send_to_superuser(bot,f'群名:{gname} 群号:{gid}\n管理员撤回了{user_card}({uid})的消息:\n'+msg)