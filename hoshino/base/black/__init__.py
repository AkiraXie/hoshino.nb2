import asyncio
from datetime import datetime, timedelta

from nonebot.adapters import Event
from nonebot.exception import FinishedException, IgnoredException
from nonebot.typing import T_State
from pytz import timezone
from sqlalchemy import select

from hoshino.command import At, UniMsg
from hoshino.core.hooks import event_preprocessor, on_startup
from hoshino.core.log import logger
from hoshino.platform import get_user_id, is_message_event
from hoshino.util.command import sucmd

from .data import (
    BlackRecord as db,  # noqa: N813  # db 为 SQLAlchemy 模型短别名（ORM 惯例），非 lowercase 误用
)
from .data import Session

_block_users: set[int] = set()


def _load_active_blocks(now: datetime) -> list:
    """读取 due_time 晚于 now 的拉黑记录（供 asyncio.to_thread 调用）。"""
    with Session() as session:
        stmt = select(db).where(db.due_time > now)
        return list(session.execute(stmt).scalars().all())


def _persist_block(uid: int, due_time: datetime) -> None:
    with Session() as session:
        session.merge(db(uid=uid, due_time=due_time))
        session.commit()


def _delete_block_rows(uid: int) -> bool:
    with Session() as session:
        stmt = select(db).where(db.uid == uid)
        rows = list(session.execute(stmt).scalars().all())
        for row in rows:
            session.delete(row)
        session.commit()
        return bool(rows)


@on_startup
async def _recover_from_db() -> None:
    """启动时从数据库恢复未过期拉黑，并安排到期自动解封。"""
    date = datetime.now(timezone("Asia/Shanghai"))
    rows = await asyncio.to_thread(_load_active_blocks, date)
    loop = asyncio.get_running_loop()
    for r in rows:
        _block_users.add(r.uid)
        # SQLAlchemy DateTime 无 timezone=True，读回是 naive（上海墙钟时间），补回时区再比较
        due_date = r.due_time.replace(tzinfo=timezone("Asia/Shanghai"))
        sec = int((due_date - date).total_seconds())
        loop.call_later(sec, lambda uid=r.uid: _block_users.discard(uid))
    logger.info("blocked users has recovered from db")


async def block_uid(uid: int, date: datetime | timedelta) -> None:
    if isinstance(date, timedelta):
        sec = int(date.total_seconds())
        due = datetime.now(timezone("Asia/Shanghai")) + date
    else:
        sec = int((date - datetime.now(timezone("Asia/Shanghai"))).total_seconds())
        due = date
    _block_users.add(uid)
    await asyncio.to_thread(_persist_block, uid, due)
    asyncio.get_running_loop().call_later(sec, lambda: _block_users.discard(uid))


async def unblock_uid(uid: int) -> bool:
    _block_users.discard(uid)
    return await asyncio.to_thread(_delete_block_rows, uid)


def _parse_ids_from_msg(msg: UniMsg | str) -> list[int]:
    """从消息中提取 ID — At 目标 + 数字文本"""
    ids: list[int] = []
    if isinstance(msg, str):
        ids.extend(int(word) for word in msg.split() if word.isdigit())
        return ids
    ids.extend(int(seg.target) for seg in msg if isinstance(seg, At))
    text = str(msg)
    ids.extend(int(word) for word in text.split() if word.isdigit())
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
        await block_uid(uid, timedelta(hours=hours))
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
        await unblock_uid(uid)
    await jiefeng.finish(f"已为{len(state['ids'])}人解封~嘿嘿嘿~")
