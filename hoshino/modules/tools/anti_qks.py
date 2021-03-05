'''
Author: AkiraXie
Date: 2021-02-13 22:24:20
LastEditors: AkiraXie
LastEditTime: 2021-03-05 01:01:39
Description: 
Github: http://github.com/AkiraXie/
'''
from hoshino import aiohttpx, Service, Bot, Event, T_State, R
qksimg = R.img('qksimg.jpg').CQcode
msg = '骑空士爪巴\n'+qksimg
sv = Service('antiqks', visible=False)


async def check_gbf(url: str) -> dict:
    resp = await aiohttpx.head(url, allow_redirects=False, timeout=5)
    h, s = resp.headers, resp.status_code
    loc = h.get('Location', None)
    ret = {'flag': False, 'loc': None}
    if not loc:
        return ret
    if s not in (301, 302):
        return ret
    ret['flag'] = 'granbluefantasy.jp' in loc
    ret['loc'] = loc
    return ret


@sv.on_regex(r'https?:\/\/[a-z0-9A-Z\.\-]{4,11}\/[a-zA-Z0-9\-]{0,10}', normal=False)
async def _(bot: Bot, event: Event, state: T_State):
    res = state['_matched']
    ret = await check_gbf(res)
    if not ret['loc']:
        return
    if ret['flag']:
        await bot.send(event, msg, at_sender=True)
    else:
        ret1 = await check_gbf(ret['loc'])
        if ret1['flag']:
            await bot.send(event, msg, at_sender=True)


@sv.on_keyword("granbluefantasy.jp")
async def _(bot: Bot, event: Event):
    await bot.send(event, msg, at_sender=True)
