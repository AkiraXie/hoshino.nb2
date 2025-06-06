import asyncio
import time
from hoshino import sucmd, Bot, driver
from hoshino.util import send_to_superuser
from asyncio import all_tasks
from datetime import datetime, UTC
import psutil

showcmd = sucmd("状态", aliases={"serverinfo", "stat"})
epoch = datetime.fromtimestamp(0, UTC)


def get_gocq_process():
    _p = None
    for ps in psutil.process_iter():
        if "go-cq" in ps.name() or "gocq" in ps.name():
            _p = psutil.Process(ps.pid)
            break
    return _p


def get_lag_process():
    _p = None
    for ps in psutil.process_iter():
        if "Lagrange" in ps.name():
            _p = psutil.Process(ps.pid)
            break
    return _p


async def get_stat():
    p = psutil.Process()
    pp = get_gocq_process()
    pl = get_lag_process()
    name = "go-cqhttp" if pp else "Lagrange"
    ppp = pp if pp else pl
    if ppp:
        ppp.cpu_percent()
    tasks = all_tasks()
    p.cpu_percent()
    await asyncio.sleep(1)
    cpu_p = p.cpu_percent()
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
        f"服务运行时间: {datetime.fromtimestamp(live_time, UTC) - epoch}",
        f"磁盘使用: {dp}%  {du:.2f}GB/{dt:.2f}GB",
    ]
    if not ppp:
        return "\n".join(msg)
    cpu_p1 = ppp.cpu_percent()
    mem1 = ppp.memory_full_info().uss / 1024.0 / 1024.0
    p_live_time = time.time() - ppp.create_time()
    msg.extend(
        [
            f"{name} CPU使用: {cpu_p1}%",
            f"{name} 内存使用: {mem1:.2f}MB",
            f"{name} 运行时间: {datetime.fromtimestamp(p_live_time, UTC) - epoch}",
        ]
    )
    return "\n".join(msg)


@showcmd.handle()
async def _():
    await showcmd.finish(await get_stat())


@driver.on_bot_connect
async def _(bot: Bot):
    await send_to_superuser(await get_stat())
