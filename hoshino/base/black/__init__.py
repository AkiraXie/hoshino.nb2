'''
Author: AkiraXie
Date: 2021-02-05 14:34:41
LastEditors: AkiraXie
LastEditTime: 2021-02-05 20:10:12
Description: 
Github: http://github.com/AkiraXie/
'''
from loguru import logger
from nonebot.adapters.cqhttp.event import MessageEvent
from nonebot.message import event_preprocessor
from nonebot.exception import FinishedException, IgnoredException
from nonebot.permission import SUPERUSER
from nonebot.rule import to_me
from hoshino import Bot, Event
from hoshino.typing import T_State
from hoshino.util import sucmd, parse_qq
from datetime import datetime, timedelta
from typing import Union
from pytz import timezone
from .data import black
BANNED_WORD = {
    'rbq', 'RBQ', '憨批', '废物', '死妈', '崽种', '傻逼', '傻逼玩意',
    '没用东西', '傻B', '傻b', 'SB', 'sb', '煞笔', 'cnm', '爬', 'kkp',
    'nmsl', 'D区', '口区', '我是你爹', 'nmbiss', '弱智', '给爷爬', '杂种爬', '爪巴'
}


def block_uid(uid: int, date: Union[datetime, timedelta]):
    if isinstance(date, timedelta):
        date = datetime.now(timezone('Asia/Shanghai'))+date
    black.replace(uid=uid, due_time=date).execute()


def check_uid(uid: int, date: datetime) -> bool:
    res = black.get_or_none(
        black.uid == uid, black.due_time.to_timestamp() > date.timestamp())
    if res:
        return False
    else:
        return True


def unblock_uid(uid: int) -> bool:
    res = black.delete().where(black.uid == uid).execute()
    return bool(res)


@event_preprocessor
async def _(bot: Bot, event: Event, state: T_State):
    if not isinstance(event, MessageEvent):
        return
    uid = int(event.user_id)
    if not check_uid(uid, datetime.now(timezone('Asia/Shanghai'))):
        raise IgnoredException('This user is blocked')
    if event.is_tome():
        for bw in BANNED_WORD:
            if bw in event.get_plaintext():
                if await SUPERUSER(bot, event):
                    await bot.send(event, '虽然你骂我但是我好像也不讨厌你~', at_sender=True)
                    return
                block_uid(uid, timedelta(hours=12))
                await bot.send(event, '拉黑了,再见了您~', at_sender=True)
                break

lahei = sucmd('拉黑', to_me(),aliases={'block', '封禁', 'ban',
                             '禁言', '小黑屋', 'b了'}, handlers=[parse_qq])
jiefeng = sucmd('解封',to_me(), aliases={'解禁'}, handlers=[parse_qq])


@lahei.got('ids', prompt='请输入要拉黑的id,并用空格隔开~\n在群聊中，还支持直接at哦~', args_parser=parse_qq)
@lahei.got('hours', '请输入要拉黑的小时数')
async def _(bot: Bot, event: Event, state: T_State):
    if not state['ids']:
        raise FinishedException
    for uid in state['ids']:
        block_uid(uid, timedelta(hours=int(state['hours'])))
    await lahei.finish(f'已拉黑{len(state["ids"])}人{state["hours"]}小时~，嘿嘿嘿~')


@jiefeng.got('ids', prompt='请输入要解封的id,并用空格隔开~\n在群聊中，还支持直接at哦~', args_parser=parse_qq)
async def _(bot: Bot, event: Event, state: T_State):
    if not state['ids']:
        raise FinishedException
    for uid in state['ids']:
        unblock_uid(uid)
    await jiefeng.finish(f'已为{len(state["ids"])}人解封~，嘿嘿嘿~')
