import asyncio
from nonebot.adapters.onebot.v11.event import MessageEvent
from nonebot.message import event_preprocessor
from nonebot.exception import FinishedException, IgnoredException
from hoshino import Bot, Event, driver
from nonebot.typing import T_State
from hoshino.util import sucmd, parse_qq
from hoshino.log import logger
from datetime import datetime, timedelta
from typing import Union
from pytz import timezone
from .data import black as db, Session
from sqlalchemy import select


_block_users = set()


@driver.on_startup
async def _():
    date = datetime.now(timezone("Asia/Shanghai"))
    with Session() as session:
        stmt = select(db).where(db.due_time > date)
        rows = session.execute(stmt).scalars().all()
        loop = asyncio.get_event_loop()
        for r in rows:
            _block_users.add(r.uid)
            due_date = r.due_time
            sec = int((due_date - date).total_seconds())
            loop.call_later(sec, lambda: _block_users.remove(r.uid))
    logger.info("blocked users has recovered from db")


def block_uid(uid: int, date: Union[datetime, timedelta]):
    if isinstance(date, timedelta):
        sec = int(date.total_seconds())
        date = datetime.now(timezone("Asia/Shanghai")) + date
    else:
        sec = int((date - datetime.now(timezone("Asia/Shanghai"))).total_seconds())
    _block_users.add(uid)
    with Session() as session:
        obj = db(uid=uid, due_time=date)
        session.merge(obj)
        session.commit()
    loop = asyncio.get_event_loop()
    loop.call_later(sec, lambda: _block_users.remove(uid))


def unblock_uid(uid: int) -> bool:
    _block_users.remove(uid)
    with Session() as session:
        stmt = select(db).where(db.uid == uid)
        rows = session.execute(stmt).scalars().all()
        for row in rows:
            session.delete(row)
        res = len(rows) > 0
        session.commit()
    return res


@event_preprocessor
async def _(bot: Bot, event: Event, state: T_State):
    if not isinstance(event, MessageEvent):
        return
    uid = int(event.user_id)
    if uid in _block_users:
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
