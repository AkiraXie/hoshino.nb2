from nonebot import on_command
from nonebot.rule import to_me
from nonebot.typing import T_State
from nonebot.adapters import Bot, Event
from nonebot.adapters.onebot.v11.message import Message
from hoshino import hsn_config

zai = on_command(
    "zai",
    aliases={"在?", "在？", "在吗", "在么？", "在嘛", "在嘛？"},
    rule=to_me(),
    block=True,
)


@zai.handle()
async def handle_zai(bot: Bot):
    if zaitext := hsn_config.zai:
        await zai.finish(str(zaitext))
    await zai.finish(Message("はい！私はいつも貴方の側にいますよ！"))
