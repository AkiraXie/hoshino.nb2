from hoshino import Bot, config as config
from nonebot import get_driver

driver = get_driver()


@driver.on_bot_connect
async def _(bot: Bot):
    for su in config.superusers:
        await bot.send_private_msg(user_id=int(su), message="生命周期上线~")
