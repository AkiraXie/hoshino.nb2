"""
Author: AkiraXie
LastEditTime: 2022-02-16 22:52:17
LastEditors: AkiraXie
GitHub: https://github.com/AkiraXie
"""
from hoshino import Service, Bot, Event, T_State, Message
from hoshino.rule import ArgumentParser
from hoshino.util import Cooldown
from hoshino.util.playwrights import get_pcr_shidan

sv = Service("shindan", visible=False, enable_on_default=False)
parser = ArgumentParser()
parser.add_argument("-n", "--name", type=str)


@sv.on_shell_command("shindan", parser=parser, aliases={"pcr女友", "PCR女友"})
async def _(bot: Bot, event: Event, state: T_State,_=Cooldown(60,prompt="您的查询将在60秒后可用")):
    await bot.send(event, "正在生成你的PCR女朋友图中...")
    if state["_args"].name:
        name = state["_args"].name
    else:
        name = event.sender.card or event.sender.nickname
    msg = f"{name}的PCR女朋友是:\n"

    try:
        ms = await get_pcr_shidan(name)
        msg += str(ms)
    except:
        ms = None
        sv.logger.error("获取shindan失败")
    if ms:
        await bot.send(event, Message(msg))
    else:
        await bot.send(event, "获取PCR女朋友失败了，悲")
