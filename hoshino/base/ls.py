from hoshino.util import sucmds
from hoshino import Bot, Event
from hoshino.service import Service, MatcherWrapper


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


lscmds = sucmds("ls", True)
lscmds.command("group", aliases={"查看群聊"}, handlers=[ls_group])
lscmds.command("friend", aliases={"查看好友"}, handlers=[ls_friend])
cmd_m = lscmds.command("matcher", aliases={"查看响应器"})
cmd_am = lscmds.command("allmatcher", aliases={"查看所有响应器"})


@cmd_m.handle()
async def _(bot: Bot, event: Event):
    svname = event.get_plaintext()
    sv = Service.get_loaded_services()[svname]
    msg = "\n".join(sv.matchers)
    await cmd_m.finish(msg)


@cmd_am.handle()
async def showall(bot: Bot):
    mws = MatcherWrapper.get_loaded_matchers()
    msg = ["该bot注册的matcher_wrapper如下:"]
    msg.extend(mws)
    await cmd_am.finish("\n".join(msg))
