'''
Author: AkiraXie
Date: 2021-01-31 15:27:52
LastEditors: AkiraXie
LastEditTime: 2021-04-15 15:05:30
Description: 
Github: http://github.com/AkiraXie/
'''
from nonebot.exception import FinishedException
from nonebot.plugin import require
from hoshino.typing import T_State
from hoshino import Event, Bot, Message, MessageSegment
from hoshino.util import concat_pic, pic2b64, FreqLimiter
from hoshino.service import Service
import re
Chara = require('chara').Chara
sv = Service('pcr-arena')
from .arena import do_query
lmt = FreqLimiter(5)

aliases = {'怎么拆', '怎么解', '怎么打', '如何拆', '如何解', '如何打',
           '怎麼拆', '怎麼解', '怎麼打', 'jjc查询', 'jjc查詢', '拆'}
aliases_b = set('b' + a for a in aliases) | set('国' +
                                                a for a in aliases) | set('B' + a for a in aliases)
aliases_b |= set('b服' + a for a in aliases) | set('国服' +
                                                  a for a in aliases) | set('B服' + a for a in aliases)
aliases_tw = set('台' + a for a in aliases) | set('台服' + a for a in aliases)
aliases_jp = set('日' + a for a in aliases) | set('日服' + a for a in aliases)


async def parse_query(bot: Bot, event: Event, state: T_State):
    argv = event.get_plaintext().strip()
    if not argv:
        return
    argv = re.sub(r'[?？，,_]', '', argv)
    defen, unknown = Chara.parse_team(argv)
    if unknown:
        await bot.send(event, f'无法识别"{unknown}",请仅输入角色名规范查询')
        raise FinishedException
    if 5 != len(defen) and 0 != len(defen):
        await bot.send(event, '由于pcrdfans.com的限制，编队必须为5个角色', call_header=True)
        raise FinishedException
    if len(defen) != len(set(defen)):
        await bot.send(event, '编队中出现重复角色', call_header=True)
        raise FinishedException
    if 1004 in defen:
        await bot.send(event, '\n⚠️您正在查询普通版炸弹人\n※万圣版可用万圣炸弹人/瓜炸等别称', call_header=True)
    state['defen'] = defen


jjc = sv.on_command('竞技场查询', aliases=aliases, only_to_me=False,
                    only_group=False, state={'region': 1},  handlers=[parse_query])
bjjc = sv.on_command('b竞技场查询', aliases=aliases_b, only_to_me=False,
                     only_group=False,  state={'region': 2}, handlers=[parse_query])
tjjc = sv.on_command('台竞技场查询', aliases=aliases_tw, only_to_me=False,
                     only_group=False, state={'region': 3},  handlers=[parse_query])
jjjc = sv.on_command('日竞技场查询', aliases=aliases_jp, only_to_me=False,
                     only_group=False, state={'region': 4},  handlers=[parse_query])


@jjc.got('defen', '请输入需要查询的防守队伍,无需空格隔开', parse_query)
@bjjc.got('defen', '请输入需要查询的防守队伍,无需空格隔开', parse_query)
@tjjc.got('defen', '请输入需要查询的防守队伍,无需空格隔开', parse_query)
@jjjc.got('defen', '请输入需要查询的防守队伍,无需空格隔开', parse_query)
async def query(bot: Bot, event: Event, state: T_State):
    if not state['defen']:
        raise FinishedException
    sv.logger.info('Doing query...')
    try:
        res = await do_query(state['defen'], state['region'])

    except Exception as e:
        sv.logger.exception(e)

    sv.logger.info('Got response!')
    if res is None:
        await bot.send(event,
                       '查询出错，请再次查询\n如果多次查询失败，请先移步pcrdfans.com进行查询，并可联系维护组', call_header=True)
        raise FinishedException
    if not len(res):
        await bot.send(event,
                       '抱歉没有查询到解法\n※没有作业说明随便拆 发挥你的想象力～★\n作业上传请前往pcrdfans.com', call_header=True)
        raise FinishedException
    res = res[:min(6, len(res))]
    sv.logger.info('Arena generating picture...')
    atk_team = [Chara.gen_team_pic(team=entry['atk'], text="\n".join([
        f" {entry['up']} ",
        f" {entry['down']} ",
    ])) for entry in res]
    atk_team = concat_pic(atk_team)
    atk_team = pic2b64(atk_team)
    atk_team = MessageSegment.image(atk_team)
    sv.logger.info('Arena picture ready!')
    defen = state['defen']
    defen = [Chara.fromid(x).name for x in defen]
    defen = f"防守方| {' '.join(defen)}"
    msg = [
        defen,
        str(atk_team),
    ]
    msg.append('Supported by pcrdfans')
    sv.logger.debug('Arena sending result...')
    await bot.send(event, Message('\n'.join(msg)), call_header=True)
    raise FinishedException
