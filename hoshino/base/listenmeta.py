from hoshino import config as config
from hoshino.types import Bot
from hoshino.hooks import on_bot_connect


@on_bot_connect
async def _(bot: Bot):
    for su in config.superusers:
        await bot.send_private_msg(user_id=int(su), message="生命周期上线~")
