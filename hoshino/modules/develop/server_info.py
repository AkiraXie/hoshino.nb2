"""
Author: AkiraXie
Date: 2021-02-24 01:19:55
LastEditors: AkiraXie
LastEditTime: 2022-02-10 23:28:52
Description: 
Github: http://github.com/AkiraXie/
"""


from hoshino import sucmd, Bot, driver
from hoshino.util import send_to_superuser
from asyncio import all_tasks
import psutil

showcmd = sucmd("info", aliases={"serverinfo", "stat"})
p = psutil.Process()


def get_stat():
    task_num = len(all_tasks())
    cpu_p = p.cpu_percent()
    mem = p.memory_full_info()
    memu = mem.uss / 1024.0 / 1024.0
    disk = psutil.disk_usage("/")
    du, dt, dp = (
        disk.used / 1024 / 1024 / 1024,
        disk.total / 1024 / 1024 / 1024,
        disk.percent,
    )
    msg = [
        f"服务CPU使用: {cpu_p}%",
        f"服务内存使用: {memu:.2f}MB",
        f"磁盘使用: {dp}%  {du:.2f}GB/{dt:.2f}GB",
        f"服务协程数量: {task_num}",
    ]
    return "\n".join(msg)


@showcmd.handle()
async def _(bot: Bot):
    await showcmd.finish(get_stat())


@driver.on_bot_connect
async def _(bot: Bot):
    await send_to_superuser(bot, get_stat())
