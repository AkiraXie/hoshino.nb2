'''
Author: AkiraXie
Date: 2021-03-18 00:02:32
LastEditors: AkiraXie
LastEditTime: 2021-03-18 00:11:35
Description: 
Github: http://github.com/AkiraXie/
'''
url='https://v1.hitokoto.cn'
from hoshino import scheduled_job,Service,aiohttpx
sv=Service('hourcall',enable_on_default=False,visible=False)
@scheduled_job('cron',hour='*',jitter=10,id='一言报时')
async def _():
    resp =await aiohttpx.get(url)
    j=resp.json
    await sv.broadcast(j['hitokoto'],tag='一言',interval_time=0.3)