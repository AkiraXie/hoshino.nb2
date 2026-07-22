from hoshino.core.config import config as config
from nonebot.adapters import Bot
from hoshino.core.hooks import on_bot_connect
from hoshino.platform import Target, send_to_target, superuser_ids_for_bot


@on_bot_connect
async def _(bot: Bot):
    for su in superuser_ids_for_bot(bot, config.superusers):
        await send_to_target(bot, Target(str(su), private=True), "生命周期上线~")
