'''
Author: AkiraXie
Date: 2022-02-26 00:16:33
LastEditors: AkiraXie
LastEditTime: 2022-03-13 22:55:20
Description: 
Github: http://github.com/AkiraXie/
'''


from hoshino import sucmd, Bot, driver
from hoshino.util import send_to_superuser
from asyncio import all_tasks
import psutil

showcmd = sucmd("info", aliases={"serverinfo", "stat"})
p = psutil.Process()
p1 :psutil.Process = None

def refresh_gocq_process():
    global p1
    _p = None
    for ps in psutil.process_iter():
        if  "go-cq" in ps.name():
            _p = psutil.Process(ps.pid)
            break
    p1 = _p

def get_gocq_process():
    if p1:
        return p1
    else:
        refresh_gocq_process()
        return p1
    
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
        f"服务协程数量: {task_num}"
    ]
    pp = get_gocq_process()
    if not pp:
        return "\n".join(msg)
    cpu_p1 = pp.cpu_percent()
    mem1 = pp.memory_full_info().uss / 1024.0 / 1024.0
    msg.extend([f"go-cqhttp CPU使用: {cpu_p1}%", f"go-cqhttp 内存使用: {mem1:.2f}MB"])
    return "\n".join(msg)


@showcmd.handle()
async def _(bot: Bot):
    await showcmd.finish(get_stat())


@driver.on_bot_connect
async def _(bot: Bot):
    refresh_gocq_process()       
    await send_to_superuser(bot, get_stat())
