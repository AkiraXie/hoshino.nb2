from loguru import logger
from hoshino import sucmd, Bot, Event
from hoshino.typing import T_State, FinishedException
from hoshino.schedule import scheduler
from datetime import datetime
showjob = sucmd('定时任务', True, {'显示定时任务', 'showjobs'})


@showjob.handle()
async def _(bot: Bot):
    msg = ["现有定时任务如下: "]
    jobs = scheduler.get_jobs()
    for job in jobs:
        id=job.id
        trigger=job.trigger
        next_run_time=datetime.strftime(job.next_run_time,"%Y-%m-%d %H:%M:%S") if job.next_run_time else 'paused'
        msg.append(f'ID: {id}\nTrigger: {trigger}\nNext run time: {next_run_time}======')
    await showjob.send('\n'.join(msg), at_sender=True)

pausejob = sucmd('暂停定时任务', True, {'暂停任务', 'pausejob'}, state={'action': '暂停'})
resumejob = sucmd('恢复定时任务', True, {
                  '恢复任务', 'resumejob', '继续任务', '继续定时任务'}, state={'action': '恢复'})


async def parse_job(bot: Bot, event: Event, state: T_State):
    msgs = event.get_plaintext().split()
    if msgs:
        state['jobs'] = msgs.copy()
pausejob.handle()(parse_job)
resumejob.handle()(parse_job)


@resumejob.got('jobs', '请输入要恢复的定时任务id, 按空格分隔', parse_job)
@pausejob.got('jobs', '请输入要暂停的定时任务id, 按空格分隔', parse_job)
async def _(bot: Bot, event: Event, state: T_State):
    if not state.get('jobs', None):
        raise FinishedException
    flag = state['action']
    jobs = state['jobs']
    msg = []
    fail = []
    for job in jobs:
        try:
            scheduler.pause_job(job) if flag=='暂停' else scheduler.resume_job(job)
            msg.append(job)
        except Exception as e:
            logger.exception(e)
            fail.append(job)
    if fail:
        await bot.send(event, '定时任务'+'|'.join(fail)+f'{flag}失败')
    await bot.send(event, f'已{flag}定时任务:\n'+'|'.join(msg))
