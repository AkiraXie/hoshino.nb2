from hoshino import sucmd, Bot
import psutil
showcmd = sucmd('info', aliases={'serverinfo'})


@showcmd.handle()
async def _(bot: Bot):
    cpu_p = psutil.cpu_percent()
    mem = psutil.virtual_memory()
    memu, memt, memp = mem.used/1024/1024, mem.total/1024/1024, mem.percent
    disk = psutil.disk_usage('/')
    du, dt, dp = disk.used/1024/1024/1024, disk.total/1024/1024/1024, disk.percent
    msg = [f'CPU使用: {cpu_p}%',
           f'内存使用: {memp}%  {memu:.2f}MB/{memt:.2f}MB',
           f'磁盘使用: {dp}%  {du:.2f}GB/{dt:.2f}GB']
    await showcmd.finish('\n'.join(msg))
