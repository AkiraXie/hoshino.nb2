from hoshino import config as config
from hoshino.types import Bot
from hoshino.hooks import on_bot_connect
from hoshino.platform import Target, send_to_target


@on_bot_connect
async def _(bot: Bot):
    for su in config.superusers:
        await send_to_target(bot, Target(str(su), private=True), "生命周期上线~")
