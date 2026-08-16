from nonebot import on_command
from nonebot.rule import to_me

from hoshino.core.config import config

zai = on_command(
    "zai",
    aliases={"在?", "在？", "在吗", "在么？", "在嘛", "在嘛？"},
    rule=to_me(),
    block=True,
)


@zai.handle()
async def handle_zai():
    if zaitext := config.zai:
        await zai.finish(str(zaitext))
