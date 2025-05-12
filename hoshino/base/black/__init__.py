import asyncio
from nonebot.adapters.onebot.v11.event import MessageEvent
from nonebot.message import event_preprocessor
from nonebot.exception import FinishedException, IgnoredException
from nonebot.permission import SUPERUSER
from hoshino import Bot, Event, driver
from hoshino.typing import T_State
from hoshino.util import sucmd, parse_qq
from hoshino.log import logger
from datetime import datetime, timedelta
from typing import Union
from pytz import timezone
from .data import black

BANNED_WORD = {
    "rbq",
    "RBQ",
    "憨批",
    "废物",
    "死妈",
    "崽种",
    "傻逼",
    "傻逼玩意",
    "没用东西",
    "傻B",
    "傻b",
    "SB",
    "sb",
    "煞笔",
    "cnm",
    "爬",
    "kkp",
    "nmsl",
    "D区",
    "口区",
    "我是你爹",
    "nmbiss",
    "弱智",
    "给爷爬",
    "杂种爬",
    "爪巴",
}

_block_users = set()


@driver.on_startup
async def _():
    date = datetime.now(timezone("Asia/Shanghai"))
    rows = black.select().where(black.due_time.to_timestamp() > date.timestamp())
    loop = asyncio.get_event_loop()
    for r in rows:
        _block_users.add(r.uid)
        due_date = datetime.strptime(r.due_time, "%Y-%m-%d %H:%M:%S.%f%z")
        sec = (due_date - date).seconds
        loop.call_later(sec, lambda: _block_users.remove(r.uid))
    logger.info("blocked users has recovered from db")


def block_uid(uid: int, date: Union[datetime, timedelta]):
    if isinstance(date, timedelta):
        sec = date.seconds
        date = datetime.now(timezone("Asia/Shanghai")) + date
    else:
        sec = (date - datetime.now(timezone("Asia/Shanghai"))).seconds
    _block_users.add(uid)
    black.replace(uid=uid, due_time=date).execute()
    loop = asyncio.get_event_loop()
    loop.call_later(sec, lambda: _block_users.remove(uid))


def unblock_uid(uid: int) -> bool:
    _block_users.remove(uid)
    res = black.delete().where(black.uid == uid).execute()
    return bool(res)


@event_preprocessor
async def _(bot: Bot, event: Event, state: T_State):
    if not isinstance(event, MessageEvent):
        return
    uid = int(event.user_id)
    if uid in _block_users:
        raise IgnoredException("This user is blocked")
    if event.is_tome():
        text = event.get_plaintext()
        for bw in BANNED_WORD:
            if bw in text:
                if await SUPERUSER(bot, event):
                    await bot.send(
                        event, "虽然你骂我但是我好像也不讨厌你~", at_sender=True
                    )
                    raise IgnoredException("This user is blocked")
                block_uid(uid, timedelta(hours=8))
                await bot.send(event, "拉黑了,再见了您~", at_sender=True)
                raise IgnoredException("This user is blocked")


lahei = sucmd(
    "拉黑",
    True,
    aliases={"block", "封禁", "ban", "禁言", "小黑屋", "b了"},
    handlers=[parse_qq],
)
jiefeng = sucmd("解封", True, aliases={"解禁"}, handlers=[parse_qq])


@lahei.got(
    "ids",
    prompt="请输入要拉黑的id,并用空格隔开~\n在群聊中，还支持直接at哦~",
    args_parser=parse_qq,
)
@lahei.got("hours", "请输入要拉黑的小时数")
async def _(state: T_State):
    if not state.get("ids"):
        raise FinishedException
    for uid in state["ids"]:
        block_uid(uid, timedelta(hours=int(state["hours"])))
    await lahei.finish(f"已拉黑{len(state['ids'])}人{state['hours']}小时~，嘿嘿嘿~")


@jiefeng.got(
    "ids",
    prompt="请输入要解封的id,并用空格隔开~\n在群聊中，还支持直接at哦~",
    args_parser=parse_qq,
)
async def _(state: T_State):
    if not state.get("ids"):
        raise FinishedException
    for uid in state["ids"]:
        unblock_uid(uid)
    await jiefeng.finish(f"已为{len(state['ids'])}人解封~，嘿嘿嘿~")
