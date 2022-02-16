'''
Author: AkiraXie
Date: 2021-02-13 22:06:41
LastEditors: AkiraXie
LastEditTime: 2022-02-16 22:42:55
Description: 
Github: http://github.com/AkiraXie/
'''
from hoshino import Service,scheduled_job

sv = Service('pcr-arena-reminder')
svjp = Service('pcr-arena-reminder-jp', enable_on_default=False)
msg = '骑士君~准备好背刺了吗？'

@scheduled_job('cron', hour='14', minute='45',jitter=20,id='b服台服jjc提醒')
async def pcr_reminder():
    await sv.broadcast(msg, 'pcr-reminder', 0.2)

@scheduled_job('cron', hour='13', minute='45',jitter=20,id='日服jjc提醒')
async def pcr_reminder_jp():
    await svjp.broadcast(msg, 'pcr-reminder-jp', 0.2)