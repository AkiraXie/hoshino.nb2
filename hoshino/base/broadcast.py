from loguru import logger
from hoshino.util import sucmd
from hoshino import Bot, Event
from asyncio import sleep

bc = sucmd("bc", aliases={"广播", "broadcast"})


@bc.handle()
async def _(bot: Bot, event: Event):
    msg = event.get_message()
    gids = list(gdic["group_id"] for gdic in await bot.get_group_list())
    count = 0
    for gid in gids:
        await sleep(0.5)
        try:
            await bot.send_group_msg(message=msg, group_id=gid)
            count += 1
            logger.info(f"群{gid} 投递成功！")
        except Exception as e:
            logger.exception(e)
            logger.error(type(e))
            await bot.send(event, f"群{gid} 投递失败：\n {type(e)} {e}")
    await bc.finish(f"广播完成,投递成功{count}个群")
