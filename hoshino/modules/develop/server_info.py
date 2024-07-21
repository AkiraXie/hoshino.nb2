'''
Author: AkiraXie
Date: 2022-02-26 00:16:33
LastEditors: AkiraXie
LastEditTime: 2022-03-13 22:55:20
Description: 
Github: http://github.com/AkiraXie/
'''


import time
from hoshino import sucmd, Bot, driver
from hoshino.util import send_to_superuser
from asyncio import all_tasks
from datetime import datetime,timedelta,UTC
import psutil
showcmd = sucmd("info", aliases={"serverinfo", "stat"})
p = psutil.Process()
p1 :psutil.Process = None
p2 :psutil.Process = None
epoch = datetime.fromtimestamp(0,UTC)
def refresh_gocq_process():
    global p1
    _p = None
    for ps in psutil.process_iter():
        if  "go-cq" in ps.name() or "gocq" in ps.name():
            _p = psutil.Process(ps.pid)
            break     
    p1 = _p

def refresh_lag_process():
    global p2
    _p = None
    for ps in psutil.process_iter():
        if  "Lagrange" in ps.name() :
            _p = psutil.Process(ps.pid)
            break     
    p2 = _p


def get_gocq_process():
    if p1:
        return p1
    else:
        refresh_gocq_process()
        return p1


def get_lag_process():
    if p2:
        return p2
    else:
        refresh_lag_process()
        return p2

def get_stat():
    tasks = all_tasks()
    cpu_p = p.cpu_percent(1)
    mem = p.memory_full_info()
    memu = mem.uss / 1024.0 / 1024.0
    disk = psutil.disk_usage("/")
    du, dt, dp = (
        disk.used / 1024 / 1024 / 1024,
        disk.total / 1024 / 1024 / 1024,
        disk.percent,
    )
    live_time = time.time() - p.create_time()
    msg = [
        f"服务CPU使用: {cpu_p}%",
        f"服务内存使用: {memu:.2f}MB",
        f"服务协程数量: {len(tasks)}",
        f"服务运行时间: {datetime.fromtimestamp(live_time,UTC)-epoch}",
        f"磁盘使用: {dp}%  {du:.2f}GB/{dt:.2f}GB",
    ]
    pp = get_gocq_process()
    pl = get_lag_process()
    if not pp and not pl:
        return "\n".join(msg)
    name = "go-cqhttp" if pp else "Lagrange"
    p = pp if pp else pl
    cpu_p1 = p.cpu_percent(1)
    mem1 = p.memory_full_info().uss / 1024.0 / 1024.0
    p_live_time = time.time() - p.create_time()
    msg.extend([f"{name} CPU使用: {cpu_p1}%", 
                f"{name} 内存使用: {mem1:.2f}MB",
                f"{name} 运行时间: {datetime.fromtimestamp(p_live_time,UTC)-epoch}"])
    return "\n".join(msg)


@showcmd.handle()
async def _():
    await showcmd.finish(get_stat())


@driver.on_bot_connect
async def _(bot: Bot):
    refresh_gocq_process()       
    await send_to_superuser(bot, get_stat())

