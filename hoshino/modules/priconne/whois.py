'''
Author: AkiraXie
Date: 2021-01-31 03:06:03
LastEditors: AkiraXie
LastEditTime: 2022-02-16 22:42:30
Description: 
Github: http://github.com/AkiraXie/
'''

from nonebot.permission import SUPERUSER
from nonebot.exception import FinishedException
from hoshino import Service, Event, Message, Bot
from hoshino.typing import T_State
from hoshino.util import FreqLimiter
from hoshino.modules.priconne.chara import Chara
sv = Service('whois')
_lmt = FreqLimiter(5)
_lmt1 = FreqLimiter(5)
_lmt2= FreqLimiter(5)
STARDIC = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6}


async def handle_whois(bot: Bot, event: Event, state: T_State):
    uid = int(event.get_user_id())
    if not _lmt.check(uid):
        await bot.send(event, '您查询得太快了，请稍等一会儿', call_header=True)
        raise FinishedException
    _lmt.start_cd(uid)
    match = state['match']
    name = match.group(1)
    if name.isdigit():
        chara = Chara.fromid(int(name),star=0)
    else:
        chara = Chara.fromname(name, star=0)
    if chara.id == Chara.UNKNOWN:
        msg = [f'兰德索尔似乎没有叫"{name}"的人']
        if not await SUPERUSER(bot, event):
            _lmt.start_cd(uid, 300)
            msg.append('您的下次查询将于5分钟后可用')
        await bot.send(event, '\n'.join(msg), call_header=True)
        raise FinishedException
    msg = f'{chara.name}\n{chara.icon.CQcode}'
    await bot.send(event, Message(msg), call_header=True)
    raise FinishedException


whois = sv.on_regex(r'^谁是(.{1,20})$',
                    handlers=[handle_whois], only_group=False)

async def handle_lookcard(bot: Bot, event: Event, state: T_State):
    uid = int(event.get_user_id())
    if not _lmt.check(uid):
        await bot.send(event, '您查询得太快了，请稍等一会儿', call_header=True)
        raise FinishedException
    _lmt1.start_cd(uid)
    match = state['match']
    name = match.group(2)
    star = match.group(1)[0] if match.group(
        1) else match.group(3)[0] if match.group(3) else 0
    star = STARDIC.get(star, star)
    chara = Chara.fromname(name, star=int(star))
    if chara.id == Chara.UNKNOWN:
        msg = [f'兰德索尔似乎没有叫"{name}"的人']
        if not await SUPERUSER(bot, event):
            _lmt1.start_cd(uid, 300)
            msg.append('您的下次查询将于5分钟后可用')
            await bot.send(event, '\n'.join(msg), call_header=True)
            raise FinishedException

    await bot.send(event, "图片较大，请稍等片刻")
    msg = chara.card
    await bot.send(event, Message(msg), call_header=True)
    raise FinishedException
lookcard = sv.on_regex(
    r'^([1-6一二三四五六][xX星])?\s?(.*?)([1-6一二三四五六][xX星])?(立绘|卡面)$', only_group=False, handlers=[handle_lookcard])


look_en_jp_name=sv.on_regex(r'^(.{1,20})(日|英)[语文]名$',
                    only_group=False)


@look_en_jp_name
async def _(bot: Bot, event: Event, state: T_State):
    uid = int(event.get_user_id())
    if not _lmt2.check(uid):
        await bot.send(event, '您查询得太快了，请稍等一会儿', call_header=True)
        raise FinishedException
    _lmt2.start_cd(uid)
    match = state['match']
    name = match.group(1)
    region = match.group(2)
    if name.isdigit():
        chara = Chara.fromid(int(name),star=0)
    else:
        chara = Chara.fromname(name, star=0)
    if chara.id == Chara.UNKNOWN:
        msg = [f'兰德索尔似乎没有叫"{name}"的人']
        if not await SUPERUSER(bot, event):
            _lmt2.start_cd(uid, 300)
            msg.append('您的下次查询将于5分钟后可用')
        await bot.send(event, '\n'.join(msg), call_header=True)
        raise FinishedException
    if region == "英":
        msg = f'{chara.enname}\n{chara.icon.CQcode}'
    else :
        msg = f'{chara.jpname}\n{chara.icon.CQcode}'
    await bot.send(event, Message(msg), call_header=True)
    raise FinishedException