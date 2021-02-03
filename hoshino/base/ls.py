'''
Author: AkiraXie
Date: 2021-02-01 13:28:02
LastEditors: AkiraXie
LastEditTime: 2021-02-02 22:25:39
Description: 
Github: http://github.com/AkiraXie/
'''
from nonebot.permission import SUPERUSER
from hoshino import Bot, Event
from nonebot import CommandGroup


async def ls_group(bot: Bot, event: Event):
    gl = await bot.get_group_list()
    msg = ["{group_id} {group_name}".format_map(g) for g in gl]
    msg = "\n".join(msg)
    msg = f"| 群号 | 群名 | 共{len(gl)}个群\n" + msg
    await bot.send(event, msg)


async def ls_friend(bot: Bot, event: Event):
    gl = await bot.get_friend_list()
    msg = ["{user_id} {nickname}".format_map(g) for g in gl]
    msg = "\n".join(msg)
    msg = f"| QQ号 | 昵称 | 共{len(gl)}个好友\n" + msg
    await bot.send(event, msg)


lscmds = CommandGroup('ls', permission=SUPERUSER)
cmd_g = lscmds.command('group',aliases={'查看群聊'},handlers=[ls_group])
cmd_f = lscmds.command('friend',aliases={'查看好友'},handlers=[ls_friend])
