'''
Author: AkiraXie
Date: 2021-01-29 18:24:41
LastEditors: AkiraXie
LastEditTime: 2021-01-31 23:51:09
Description: 
Github: http://github.com/AkiraXie/
'''

from hoshino import R, Service, Bot, Event, Message
from hoshino.typing import T_State
p1 = R.img('priconne/quick/tqian.png')
p2 = R.img('priconne/quick/tzhong.png')
p3 = R.img('priconne/quick/thou.png')
p4 = R.img+'priconne/quick/bqian.png'
p5 = R.img('priconne/quick/bzhong.png')
p6 = R.img.priconne.quick('bhou.png')
p7 = R.img('priconne/quick/rqian.png')
p8 = R.img('priconne/quick/rzhong.png')
p9 = R.img('priconne/quick/rhou.png')
yukari_pic = R.img('priconne/quick/yukari.jpg')
byk_pic = R.img('priconne/quick/banyuekan.jpg')
YUKARI = f'''{yukari_pic.CQcode}
※大圈是1动充电对象 PvP测试
※黄骑四号位例外较多
※对面羊驼或中后卫坦 有可能歪
※我方羊驼算一号位
'''
brank = (p4, p5, p6)
trank = (p1, p2, p3)
rrank = (p7, p8, p9)
posdic = {"前": 0, "中": 1, "后": 2}
serdic = {'b': brank, '国': brank, '台': trank,
          '日': rrank, 't': trank, 'j': rrank}
sv = Service('query')

rank = sv.on_regex(r'^([台国日btj]{1,3})服?([前中后]{0,3})rank表?$', only_group=0)
yukari = sv.on_command('yukari_charge', aliases={
                       '黄骑充电', '黄骑充电表', '酒鬼充电', '酒鬼充电表'}, only_group=False)
byk = sv.on_command(
    '半月刊', aliases={'活动半月刊', 'b服半月刊', '国服半月刊'}, only_group=False)


@rank.handle()
async def _(bot: Bot, event: Event, state: T_State):
    import re
    event.get_user_id
    bot.self_id
    match=re.compile(r'^([台国日btj]{1,3})服?([前中后]{0,3})rank表?$').search(str(event.get_message()))
    match=state['match']
    pos = match.group(2)
    ser = match.group(1)
    msg = ['Rank表仅供参考,以公会要求为准', '不定期更新，来源见图']
    poslist = set([posdic[i] for i in pos]) if pos else [0, 1, 2]
    serlist = set([serdic[i] for i in ser])
    for s in serlist:
        msg.extend([f'{s[p].CQcode}' for p in poslist])
    await rank.send(Message('\n'.join(msg)))


@yukari.handle()
async def _(bot: Bot):
    await yukari.finish(Message(YUKARI))


@byk.handle()
async def _(bot: Bot):
    await byk.send('图片较大，请稍等片刻')
    await byk.send(Message(byk_pic.CQcode))
