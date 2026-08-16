from asyncio import sleep

from loguru import logger
from nonebot.adapters import Bot

from hoshino.platform import get_group_list, group_target, send_to_target
from hoshino.platform.depends import EventMessage
from hoshino.util.command import sucmd

bc = sucmd("bc", aliases={"广播", "broadcast"})


@bc.handle()
async def _(bot: Bot, msg=EventMessage()):
    gids = [group["group_id"] for group in await get_group_list(bot)]
    if not gids:
        # Telegram 无法枚举机器人加入的所有聊天，空列表不代表真的没有群
        await bc.finish("没有可广播的群（Telegram 等平台无法枚举机器人加入的聊天）")
    count = 0
    for gid in gids:
        await sleep(0.5)
        try:
            await send_to_target(bot, group_target(gid), msg)
            count += 1
            logger.info(f"群{gid} 投递成功！")
        except Exception as e:
            logger.exception(e)
            logger.error(type(e))
            await bc.send(f"群{gid} 投递失败：\n {type(e)} {e}")
    await bc.finish(f"广播完成,投递成功{count}个群")
