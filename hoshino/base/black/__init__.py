import asyncio
from nonebot.exception import FinishedException, IgnoredException
from nonebot.typing import T_State
from hoshino.core.hooks import event_preprocessor, on_startup
from nonebot.adapters import Event
from hoshino.util import sucmd
from hoshino.core.log import logger
from hoshino.command import UniMsg
from hoshino.platform import (
    get_user_id,
    is_message_event,
)
from hoshino.command import At
from datetime import datetime, timedelta
from pytz import timezone
from .data import black as db, Session
from sqlalchemy import select


_block_users = set()


@on_startup
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


def block_uid(uid: int, date: datetime | timedelta):
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


def _parse_ids_from_msg(msg: UniMsg | str) -> list[int]:
    """从消息中提取 ID — At 目标 + 数字文本"""
    ids: list[int] = []
    if isinstance(msg, str):
        for word in msg.split():
            if word.isdigit():
                ids.append(int(word))
        return ids
    for seg in msg:
        if isinstance(seg, At):
            ids.append(int(seg.target))
    text = str(msg)
    for word in text.split():
        if word.isdigit():
            ids.append(int(word))
    return ids


@event_preprocessor
async def _(event: Event, state: T_State):
    if not is_message_event(event):
        return
    uid = get_user_id(event)
    if uid is None:
        return
    uid = int(uid)
    if uid in _block_users:
        raise IgnoredException("This user is blocked")


lahei = sucmd(
    "拉黑",
    True,
    aliases={"block", "封禁", "ban", "禁言", "小黑屋", "b了"},
)
jiefeng = sucmd("解封", True, aliases={"解禁"})


@lahei.got(
    "ids",
    prompt="请输入要拉黑的id,并用空格隔开~\n在群聊中，还支持直接at哦~",
)
async def _(state: T_State, msg: UniMsg):
    ids = _parse_ids_from_msg(msg)
    if not ids:
        await lahei.reject("请提供要拉黑的id,并用空格隔开~\n在群聊中，还支持直接at哦~")
    state["ids"] = ids


@lahei.got("hours", "请输入要拉黑的小时数")
async def _(state: T_State):
    if not state.get("ids"):
        raise FinishedException
    for uid in state["ids"]:
        hours = int(str(state["hours"]))
        block_uid(uid, timedelta(hours=hours))
    await lahei.finish(f"已拉黑{len(state['ids'])}人{state['hours']}小时~嘿嘿嘿~")


@jiefeng.got(
    "ids",
    prompt="请输入要解封的id,并用空格隔开~\n在群聊中，还支持直接at哦~",
)
async def _(state: T_State, msg: UniMsg):
    ids = _parse_ids_from_msg(msg)
    if not ids:
        await jiefeng.reject("请提供要解封的id,并用空格隔开~\n在群聊中，还支持直接at哦~")
    state["ids"] = ids


@jiefeng.handle()
async def _(state: T_State):
    if not state.get("ids"):
        raise FinishedException
    for uid in state["ids"]:
        unblock_uid(uid)
    await jiefeng.finish(f"已为{len(state['ids'])}人解封~嘿嘿嘿~")
