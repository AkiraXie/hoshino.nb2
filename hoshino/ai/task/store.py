"""Task 产品事实源：Task/TaskRun/Approval/Event/Outbox/Policy/Workspace/Snapshot。

表类继承 ``ai/store.py`` 的共享 ``Base``，DDL 经同一 ``on_serial_startup`` 建表。
CRUD 用同步 SQLAlchemy；创建事务显式 ``IMMEDIATE``（单写者）串行化 check-and-insert，
满足 plan 6.1 的并发 cooldown 要求。
"""

from __future__ import annotations

import json
import time
import uuid
from typing import Any

from sqlalchemy import event as sa_event
from sqlalchemy import func, select
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Boolean, Float, Integer, Text

from .. import store as ai_store

# 等待 SQLite 写锁最多 5s，写冲突时重试而非立即抛错。
sa_event.listen(
    ai_store.engine,
    "connect",
    lambda dbapi_connection, connection_record: dbapi_connection.execute(
        "PRAGMA busy_timeout=5000"
    ),
)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def _now() -> float:
    return time.time()


def _begin_immediate(session) -> None:
    """在事务起点发出 ``BEGIN IMMEDIATE``（SQLite 单写者写锁）。

    SQLAlchemy 2.x 的 sqlite 方言静态拒绝 ``isolation_level="IMMEDIATE"``（只认
    READ UNCOMMITTED / SERIALIZABLE / AUTOCOMMIT），因此用原生 SQL 抢占写锁：
    并发会话在 BEGIN 处即等待到前一事务 commit 后才读到对方写入，从而串行化
    cooldown check-and-insert 与 TaskRun claim（plan 6.1/11）。
    """
    session.connection().exec_driver_sql("BEGIN IMMEDIATE")


def _context_to_str(context_json: str | dict[str, Any]) -> str:
    """context_json 列统一存 JSON 字符串；调用方可传 ``TaskContext.to_json()`` dict。"""
    if isinstance(context_json, dict):
        return json.dumps(context_json, ensure_ascii=False)
    return context_json or "{}"


# ---------------------------------------------------------------- 表


class AITask(ai_store.Base):
    __tablename__ = "ai_tasks"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    kind: Mapped[str] = mapped_column(Text, nullable=False, default="research")
    prompt: Mapped[str] = mapped_column(Text, nullable=False, default="")
    scope_key: Mapped[str] = mapped_column(Text, nullable=False, default="")
    creator_id: Mapped[str] = mapped_column(Text, nullable=False, default="")
    target_json: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # 创建时的 adapter（platform_key），outbox 派发用于挑选同适配器的 bot。
    adapter_name: Mapped[str] = mapped_column(Text, nullable=False, default="")
    provider_id: Mapped[str] = mapped_column(Text, nullable=False, default="")
    model: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(Text, nullable=False, default="created")
    failure_reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    output_json: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[float] = mapped_column(Float, nullable=False, default=_now)
    updated_at: Mapped[float] = mapped_column(Float, nullable=False, default=_now)
    completed_at: Mapped[float | None] = mapped_column(
        Float, nullable=True, default=None
    )


class AITaskRun(ai_store.Base):
    __tablename__ = "ai_task_runs"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    task_id: Mapped[str] = mapped_column(Text, nullable=False, default="")
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    state: Mapped[str] = mapped_column(Text, nullable=False, default="queued")
    lease_owner: Mapped[str] = mapped_column(Text, nullable=False, default="")
    lease_expiry: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    heartbeat_at: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    agent_run_id: Mapped[str] = mapped_column(Text, nullable=False, default="")
    conversation_id: Mapped[str] = mapped_column(Text, nullable=False, default="")
    context_json: Mapped[str] = mapped_column(Text, nullable=False, default="")
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_retry_at: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    last_error: Mapped[str] = mapped_column(Text, nullable=False, default="")
    started_at: Mapped[float | None] = mapped_column(Float, nullable=True, default=None)
    finished_at: Mapped[float | None] = mapped_column(
        Float, nullable=True, default=None
    )


class AITaskApproval(ai_store.Base):
    __tablename__ = "ai_task_approvals"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    task_id: Mapped[str] = mapped_column(Text, nullable=False, default="")
    task_run_id: Mapped[str] = mapped_column(Text, nullable=False, default="")
    agent_run_id: Mapped[str] = mapped_column(Text, nullable=False, default="")
    tool_call_id: Mapped[str] = mapped_column(Text, nullable=False, default="")
    tool_name: Mapped[str] = mapped_column(Text, nullable=False, default="")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    param_hash: Mapped[str] = mapped_column(Text, nullable=False, default="")
    param_summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    risk_reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    state: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    creator_id: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[float] = mapped_column(Float, nullable=False, default=_now)
    expires_at: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    resolved_at: Mapped[float | None] = mapped_column(
        Float, nullable=True, default=None
    )


class AITaskEvent(ai_store.Base):
    __tablename__ = "ai_task_events"

    seq: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_type: Mapped[str] = mapped_column(Text, nullable=False, default="")
    task_id: Mapped[str] = mapped_column(Text, nullable=False, default="")
    task_run_id: Mapped[str] = mapped_column(Text, nullable=False, default="")
    agent_run_id: Mapped[str] = mapped_column(Text, nullable=False, default="")
    scope_key: Mapped[str] = mapped_column(Text, nullable=False, default="")
    payload_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    ts: Mapped[float] = mapped_column(Float, nullable=False, default=_now)


class AITaskOutbox(ai_store.Base):
    __tablename__ = "ai_task_outbox"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_type: Mapped[str] = mapped_column(Text, nullable=False, default="")
    task_id: Mapped[str] = mapped_column(Text, nullable=False, default="")
    sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    target_json: Mapped[str] = mapped_column(Text, nullable=False, default="")
    payload_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_retry_at: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    sent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_error: Mapped[str] = mapped_column(Text, nullable=False, default="")


class AIScopeTaskPolicy(ai_store.Base):
    __tablename__ = "ai_scope_task_policies"

    scope_key: Mapped[str] = mapped_column(Text, primary_key=True)
    creation_policy: Mapped[str] = mapped_column(
        Text, nullable=False, default="superuser"
    )
    max_concurrent: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_by: Mapped[str] = mapped_column(Text, nullable=False, default="")
    updated_at: Mapped[float] = mapped_column(Float, nullable=False, default=_now)


class AIScopeTaskWorkspace(ai_store.Base):
    __tablename__ = "ai_scope_task_workspaces"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scope_key: Mapped[str] = mapped_column(Text, nullable=False, default="")
    name: Mapped[str] = mapped_column(Text, nullable=False, default="")
    root: Mapped[str] = mapped_column(Text, nullable=False, default="")
    mode: Mapped[str] = mapped_column(Text, nullable=False, default="read_write")
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    updated_by: Mapped[str] = mapped_column(Text, nullable=False, default="")
    updated_at: Mapped[float] = mapped_column(Float, nullable=False, default=_now)


class AITaskCapabilitySnapshot(ai_store.Base):
    __tablename__ = "ai_task_capability_snapshots"

    task_id: Mapped[str] = mapped_column(Text, primary_key=True)
    snapshot_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[float] = mapped_column(Float, nullable=False, default=_now)


# ------------------------------------------------------------ 创建事务


def create_task(
    *,
    task_id: str,
    kind: str,
    prompt: str,
    scope_key: str,
    creator_id: str,
    target_json: str,
    provider_id: str,
    model: str,
    context_json: str | dict[str, Any],
    snapshot_json: str,
    event_payloads: list[dict[str, Any]],
    outbox_payloads: list[dict[str, Any]],
    adapter_name: str = "",
    cooldown_window: float = 300.0,
    bypass_cooldown: bool = False,
    task_run_id: str | None = None,
    conversation_id: str | None = None,
) -> dict[str, Any]:
    """事务化创建 Task + 初始 TaskRun + capability snapshot + 事件 + outbox。

    ``event_payloads``：``{"event_type","payload","task_run_id","agent_run_id"}``；
    ``outbox_payloads``：``{"event_type","sequence","payload"}``（target 用 task 的）。
    显式 ``IMMEDIATE`` 事务串行化 SQLite 上的 check-and-insert：并发两个 matcher
    同时进入时，第二个事务阻塞到第一个 commit 后，重读能看到新 Task，从而通过
    cooldown 拒绝（plan 6.1 不允许先查再另一个事务插入）。
    命中 cooldown 时返回 ``{"cooldown": True, "task_id", "status", "remaining"}``。
    """
    now = _now()
    with ai_store.Session() as session:
        _begin_immediate(session)
        if not bypass_cooldown and cooldown_window > 0:
            recent = (
                session.execute(
                    select(AITask)
                    .where(
                        AITask.scope_key == scope_key,
                        AITask.creator_id == creator_id,
                    )
                    .order_by(AITask.created_at.desc())
                    .limit(1)
                )
                .scalars()
                .first()
            )
            if recent is not None and now - recent.created_at < cooldown_window:
                return {
                    "cooldown": True,
                    "task_id": recent.id,
                    "status": recent.status,
                    "remaining": cooldown_window - (now - recent.created_at),
                }
        run_id = task_run_id or new_id("r")
        conv_id = conversation_id or uuid.uuid4().hex
        task = AITask(
            id=task_id,
            kind=kind,
            prompt=prompt,
            scope_key=scope_key,
            creator_id=creator_id,
            target_json=target_json,
            adapter_name=adapter_name,
            provider_id=provider_id,
            model=model,
            status="queued",
            created_at=now,
            updated_at=now,
        )
        run = AITaskRun(
            id=run_id,
            task_id=task_id,
            attempt=1,
            state="queued",
            conversation_id=conv_id,
            context_json=_context_to_str(context_json),
        )
        session.add_all([task, run])
        session.add(
            AITaskCapabilitySnapshot(
                task_id=task_id, snapshot_json=snapshot_json, created_at=now
            )
        )
        for ev in event_payloads:
            session.add(
                AITaskEvent(
                    event_type=ev["event_type"],
                    task_id=task_id,
                    task_run_id=ev.get("task_run_id", run_id),
                    agent_run_id=ev.get("agent_run_id", ""),
                    scope_key=scope_key,
                    payload_json=ev.get("payload", "{}"),
                    ts=now,
                )
            )
        for out in outbox_payloads:
            session.add(
                AITaskOutbox(
                    event_type=out["event_type"],
                    task_id=task_id,
                    sequence=out.get("sequence", 0),
                    target_json=target_json,
                    payload_json=out.get("payload", "{}"),
                    next_retry_at=now,
                )
            )
        session.commit()
        return {"task_id": task_id, "task_run_id": run_id}


# ------------------------------------------------------------ Task 查询


def _task_to_dict(row: AITask) -> dict[str, Any]:
    return {
        "id": row.id,
        "kind": row.kind,
        "prompt": row.prompt,
        "scope_key": row.scope_key,
        "creator_id": row.creator_id,
        "target_json": row.target_json,
        "adapter_name": row.adapter_name,
        "provider_id": row.provider_id,
        "model": row.model,
        "status": row.status,
        "failure_reason": row.failure_reason,
        "output_json": row.output_json,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        "completed_at": row.completed_at,
    }


def get_task(task_id: str) -> dict[str, Any] | None:
    with ai_store.Session() as session:
        row = session.get(AITask, task_id)
        return _task_to_dict(row) if row is not None else None


def list_tasks(
    scope_key: str | None = None,
    creator_id: str | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    with ai_store.Session() as session:
        stmt = select(AITask).order_by(AITask.created_at.desc()).limit(limit)
        if scope_key is not None:
            stmt = stmt.where(AITask.scope_key == scope_key)
        if creator_id is not None:
            stmt = stmt.where(AITask.creator_id == creator_id)
        return [_task_to_dict(r) for r in session.execute(stmt).scalars().all()]


def update_task_status(
    task_id: str, status: str, *, failure_reason: str = "", output_json: str = ""
) -> None:
    with ai_store.Session() as session:
        row = session.get(AITask, task_id)
        if row is None:
            return
        row.status = status
        row.updated_at = _now()
        if failure_reason:
            row.failure_reason = failure_reason
        if output_json:
            row.output_json = output_json
        if status in ("succeeded", "failed", "cancelled"):
            row.completed_at = _now()
        session.commit()


def count_active_runs(scope_key: str) -> int:
    """scope 当前未到终态的 TaskRun 数（并发 guard 用）。"""
    active = ("queued", "running", "retry_wait", "waiting_approval")
    with ai_store.Session() as session:
        stmt = (
            select(func.count(AITaskRun.id))
            .join(AITask, AITaskRun.task_id == AITask.id)
            .where(AITask.scope_key == scope_key, AITaskRun.state.in_(active))
        )
        return session.execute(stmt).scalar() or 0


def request_cancel(task_id: str, cancelled_by: str) -> bool:
    """持久化取消请求；返回是否成功写入（Task 未到终态）。"""
    with ai_store.Session() as session:
        row = session.get(AITask, task_id)
        if row is None:
            return False
        if row.status in ("succeeded", "failed", "cancelled"):
            return False
        row.status = "cancelled"
        row.failure_reason = "cancelled"
        row.updated_at = _now()
        row.completed_at = _now()
        run = (
            session.execute(select(AITaskRun).where(AITaskRun.task_id == task_id))
            .scalars()
            .all()
        )
        for r in run:
            if r.state not in ("succeeded", "failed", "cancelled"):
                r.state = "cancelled"
                r.finished_at = _now()
        session.commit()
        return True


# ------------------------------------------------------------ TaskRun


def _run_to_dict(row: AITaskRun) -> dict[str, Any]:
    return {
        "id": row.id,
        "task_id": row.task_id,
        "attempt": row.attempt,
        "state": row.state,
        "lease_owner": row.lease_owner,
        "lease_expiry": row.lease_expiry,
        "heartbeat_at": row.heartbeat_at,
        "agent_run_id": row.agent_run_id,
        "conversation_id": row.conversation_id,
        "context_json": row.context_json,
        "retry_count": row.retry_count,
        "next_retry_at": row.next_retry_at,
        "last_error": row.last_error,
        "started_at": row.started_at,
        "finished_at": row.finished_at,
    }


def get_task_run(task_run_id: str) -> dict[str, Any] | None:
    with ai_store.Session() as session:
        row = session.get(AITaskRun, task_run_id)
        return _run_to_dict(row) if row is not None else None


def get_task_run_for_task(task_id: str) -> dict[str, Any] | None:
    with ai_store.Session() as session:
        stmt = (
            select(AITaskRun)
            .where(AITaskRun.task_id == task_id)
            .order_by(AITaskRun.attempt.desc())
        )
        row = session.execute(stmt).scalars().first()
        return _run_to_dict(row) if row is not None else None


def claim_next_run(owner: str, now: float | None = None) -> dict[str, Any] | None:
    """原子 claim 一个到期的 queued/retry_wait TaskRun。

    只能用条件 UPDATE 把仍为 queued/retry_wait 且已到期的行置为 running，
    更新行数为 1 才获得 lease（plan 11）。SQLAlchemy 同步会话里用事务化
    ``select_for_update`` 不可用（SQLite 无行锁），退化为：
    SELECT（不锁）+ IMMEDIATE 事务里 UPDATE … WHERE state IN (...) AND next_retry_at <= now
    由 ``UPDATE`` 返回 rowcount==1 判断是否获得。
    """
    now = now or _now()
    with ai_store.Session() as session:
        _begin_immediate(session)
        stmt = (
            select(AITaskRun)
            .where(
                AITaskRun.state.in_(("queued", "retry_wait")),
                AITaskRun.next_retry_at <= now,
            )
            .order_by(AITaskRun.next_retry_at.asc())
            .limit(1)
        )
        row = session.execute(stmt).scalars().first()
        if row is None:
            return None
        # IMMEDIATE 事务已持有写锁，另一个并发 claim 会阻塞到本事务结束；
        # 结束前它重读不会看到被改的行（同一写者串行化）。
        if row.state not in ("queued", "retry_wait"):
            return None
        row.state = "running"
        row.lease_owner = owner
        row.lease_expiry = now + 120.0
        row.heartbeat_at = now
        row.started_at = row.started_at or now
        session.commit()
        return _run_to_dict(row)


def heartbeat(
    task_run_id: str,
    expiry: float,
    now: float | None = None,
    owner: str | None = None,
) -> bool:
    """续租：仅当 run 仍为 running 且 lease 仍归指定 owner 时更新。

    owner 缺省时不校验（兼容旧调用）；scheduler 传入 claim 时的 owner，防止
    lease 过期被重新 claim 后旧 worker 继续续租造成双执行。
    """
    now = now or _now()
    with ai_store.Session() as session:
        row = session.get(AITaskRun, task_run_id)
        if row is None or row.state != "running":
            return False
        if owner is not None and row.lease_owner != owner:
            return False
        row.lease_expiry = expiry
        row.heartbeat_at = now
        session.commit()
        return True


def update_run_state(
    task_run_id: str,
    state: str,
    *,
    agent_run_id: str = "",
    retry_count: int | None = None,
    next_retry_at: float | None = None,
    last_error: str = "",
    context_json: str | dict[str, Any] | None = None,
) -> bool:
    with ai_store.Session() as session:
        row = session.get(AITaskRun, task_run_id)
        if row is None:
            return False
        row.state = state
        if agent_run_id:
            row.agent_run_id = agent_run_id
        if retry_count is not None:
            row.retry_count = retry_count
        if next_retry_at is not None:
            row.next_retry_at = next_retry_at
        if last_error:
            row.last_error = last_error
        if context_json is not None:
            row.context_json = _context_to_str(context_json)
        if state in ("succeeded", "failed", "cancelled"):
            row.finished_at = _now()
        session.commit()
        return True


def mark_interrupted_expired(now: float | None = None) -> int:
    """启动恢复：把 lease 过期的 running 标记为 interrupted。"""
    now = now or _now()
    with ai_store.Session() as session:
        stmt = select(AITaskRun).where(
            AITaskRun.state == "running", AITaskRun.lease_expiry < now
        )
        rows = session.execute(stmt).scalars().all()
        for row in rows:
            row.state = "interrupted"
        session.commit()
        return len(rows)


def requeue_interrupted(now: float | None = None) -> int:
    """把可安全重跑的 interrupted 重新入队（沿用同一 TaskRun，不增加 attempt）。"""
    now = now or _now()
    with ai_store.Session() as session:
        _begin_immediate(session)
        rows = (
            session.execute(select(AITaskRun).where(AITaskRun.state == "interrupted"))
            .scalars()
            .all()
        )
        for row in rows:
            row.state = "queued"
            row.next_retry_at = now
        session.commit()
        return len(rows)


def create_next_attempt(task_id: str) -> dict[str, Any] | None:
    """内部重试耗尽后创建 attempt+1 的新 TaskRun（plan 6.3 业务重试）。

    新 run 沿用上一 run 的 conversation 与 context（含消息历史）；Task 回 queued。
    返回新 run 概要；Task 不存在返回 None。
    """
    now = _now()
    with ai_store.Session() as session:
        _begin_immediate(session)
        task = session.get(AITask, task_id)
        if task is None:
            return None
        prev = (
            session.execute(
                select(AITaskRun)
                .where(AITaskRun.task_id == task_id)
                .order_by(AITaskRun.attempt.desc())
            )
            .scalars()
            .first()
        )
        attempt = (prev.attempt if prev is not None else 0) + 1
        # conversation 以 context 内冻结的真实值优先（scheduler 运行后会更新 ctx，
        # 而 run 表的 conversation_id 列不随之刷新）；context 无效则退回旧列值。
        conversation_id = uuid.uuid4().hex
        context_json = prev.context_json if prev is not None else "{}"
        if prev is not None:
            try:
                prev_ctx = json.loads(prev.context_json or "{}")
                conversation_id = (
                    prev_ctx.get("conversation_id") or prev.conversation_id
                )
            except (ValueError, TypeError):
                conversation_id = prev.conversation_id
        run = AITaskRun(
            id=new_id("r"),
            task_id=task_id,
            attempt=attempt,
            state="queued",
            conversation_id=conversation_id,
            context_json=context_json,
            next_retry_at=now,
        )
        session.add(run)
        task.status = "queued"
        task.updated_at = now
        session.commit()
        return {"task_id": task_id, "task_run_id": run.id, "attempt": attempt}


# ------------------------------------------------------------ Approval


def create_approval(
    *,
    approval_id: str,
    task_id: str,
    task_run_id: str,
    agent_run_id: str,
    tool_call_id: str,
    tool_name: str,
    version: int,
    param_hash: str,
    param_summary: str,
    risk_reason: str,
    creator_id: str,
    expires_at: float,
) -> None:
    with ai_store.Session() as session:
        session.add(
            AITaskApproval(
                id=approval_id,
                task_id=task_id,
                task_run_id=task_run_id,
                agent_run_id=agent_run_id,
                tool_call_id=tool_call_id,
                tool_name=tool_name,
                version=version,
                param_hash=param_hash,
                param_summary=param_summary,
                risk_reason=risk_reason,
                state="pending",
                creator_id=creator_id,
                expires_at=expires_at,
            )
        )
        session.commit()


def get_pending_approval(task_run_id: str, tool_call_id: str) -> dict[str, Any] | None:
    with ai_store.Session() as session:
        stmt = select(AITaskApproval).where(
            AITaskApproval.task_run_id == task_run_id,
            AITaskApproval.tool_call_id == tool_call_id,
            AITaskApproval.state == "pending",
        )
        row = session.execute(stmt).scalars().first()
        return _approval_to_dict(row) if row is not None else None


def list_approvals(task_id: str) -> list[dict[str, Any]]:
    with ai_store.Session() as session:
        stmt = (
            select(AITaskApproval)
            .where(AITaskApproval.task_id == task_id)
            .order_by(AITaskApproval.created_at)
        )
        return [_approval_to_dict(r) for r in session.execute(stmt).scalars().all()]


def get_approval(approval_id: str) -> dict[str, Any] | None:
    with ai_store.Session() as session:
        row = session.get(AITaskApproval, approval_id)
        return _approval_to_dict(row) if row is not None else None


def resolve_approval(
    approval_id: str,
    state: str,
    resolved_by: str,
    now: float | None = None,
) -> bool:
    with ai_store.Session() as session:
        row = session.get(AITaskApproval, approval_id)
        if row is None or row.state != "pending":
            return False
        row.state = state
        row.resolved_at = now or _now()
        session.commit()
        return True


def expire_approvals(now: float | None = None) -> list[dict[str, Any]]:
    """把到期的 pending approval 标为 expired，返回它们关联的 (task_run, tool_call)。"""
    now = now or _now()
    expired: list[dict[str, Any]] = []
    with ai_store.Session() as session:
        stmt = select(AITaskApproval).where(
            AITaskApproval.state == "pending", AITaskApproval.expires_at < now
        )
        rows = session.execute(stmt).scalars().all()
        for row in rows:
            row.state = "expired"
            row.resolved_at = now
            expired.append(_approval_to_dict(row))
        session.commit()
        return expired


def _approval_to_dict(row: AITaskApproval) -> dict[str, Any]:
    return {
        "id": row.id,
        "task_id": row.task_id,
        "task_run_id": row.task_run_id,
        "agent_run_id": row.agent_run_id,
        "tool_call_id": row.tool_call_id,
        "tool_name": row.tool_name,
        "version": row.version,
        "param_hash": row.param_hash,
        "param_summary": row.param_summary,
        "risk_reason": row.risk_reason,
        "state": row.state,
        "creator_id": row.creator_id,
        "created_at": row.created_at,
        "expires_at": row.expires_at,
        "resolved_at": row.resolved_at,
    }


# ------------------------------------------------------------ Events


def append_event(
    event_type: str,
    *,
    task_id: str,
    task_run_id: str = "",
    agent_run_id: str = "",
    scope_key: str = "",
    payload: str = "{}",
) -> int:
    with ai_store.Session() as session:
        row = AITaskEvent(
            event_type=event_type,
            task_id=task_id,
            task_run_id=task_run_id,
            agent_run_id=agent_run_id,
            scope_key=scope_key,
            payload_json=payload,
            ts=_now(),
        )
        session.add(row)
        session.commit()
        return row.seq


def list_events(task_id: str, limit: int = 100) -> list[dict[str, Any]]:
    with ai_store.Session() as session:
        stmt = (
            select(AITaskEvent)
            .where(AITaskEvent.task_id == task_id)
            .order_by(AITaskEvent.seq.asc())
            .limit(limit)
        )
        return [
            {
                "seq": r.seq,
                "event_type": r.event_type,
                "task_run_id": r.task_run_id,
                "agent_run_id": r.agent_run_id,
                "payload_json": r.payload_json,
                "ts": r.ts,
            }
            for r in session.execute(stmt).scalars().all()
        ]


# ------------------------------------------------------------ Outbox


def outbox_enqueue(
    *,
    event_type: str,
    task_id: str,
    sequence: int,
    target_json: str,
    payload: str = "{}",
    next_retry_at: float | None = None,
) -> None:
    with ai_store.Session() as session:
        session.add(
            AITaskOutbox(
                event_type=event_type,
                task_id=task_id,
                sequence=sequence,
                target_json=target_json,
                payload_json=payload,
                next_retry_at=next_retry_at or _now(),
            )
        )
        session.commit()


def outbox_next_sequence(task_id: str) -> int:
    """返回该 task 下一个 outbox 序号（幂等键 (task_id, event_type, sequence)）。"""
    with ai_store.Session() as session:
        stmt = select(func.max(AITaskOutbox.sequence)).where(
            AITaskOutbox.task_id == task_id
        )
        return (session.execute(stmt).scalar() or 0) + 1


def outbox_pending(limit: int = 50) -> list[dict[str, Any]]:
    with ai_store.Session() as session:
        stmt = (
            select(AITaskOutbox)
            .where(
                AITaskOutbox.sent.is_(False),
                AITaskOutbox.next_retry_at <= _now(),
            )
            .order_by(AITaskOutbox.id.asc())
            .limit(limit)
        )
        return [
            {
                "id": r.id,
                "event_type": r.event_type,
                "task_id": r.task_id,
                "sequence": r.sequence,
                "target_json": r.target_json,
                "payload_json": r.payload_json,
                "attempt": r.attempt,
                "last_error": r.last_error,
            }
            for r in session.execute(stmt).scalars().all()
        ]


def outbox_mark_sent(outbox_id: int) -> None:
    with ai_store.Session() as session:
        row = session.get(AITaskOutbox, outbox_id)
        if row is not None:
            row.sent = True
            session.commit()


def outbox_mark_retry(
    outbox_id: int,
    error: str,
    next_retry_at: float | None = None,
    max_attempts: int = 5,
) -> None:
    """记录一次投递失败；超过 max_attempts 后放弃重试（不回滚 Task 终态）。"""
    with ai_store.Session() as session:
        row = session.get(AITaskOutbox, outbox_id)
        if row is not None:
            row.attempt += 1
            if row.attempt >= max_attempts:
                # 放弃：置为永不满足的重试时间，last_error 记录原因。
                row.last_error = f"{error}（已放弃：重试 {row.attempt} 次）"
                row.next_retry_at = float("inf")
            else:
                row.last_error = error
                row.next_retry_at = (
                    next_retry_at if next_retry_at is not None else _now() + 60.0
                )
        session.commit()


# ------------------------------------------------------------ Policy


def get_scope_policy(scope_key: str) -> dict[str, Any]:
    with ai_store.Session() as session:
        row = session.get(AIScopeTaskPolicy, scope_key)
        if row is None:
            return {
                "scope_key": scope_key,
                "creation_policy": "superuser",
                "max_concurrent": 0,
                "updated_by": "",
            }
        return {
            "scope_key": row.scope_key,
            "creation_policy": row.creation_policy,
            "max_concurrent": row.max_concurrent,
            "updated_by": row.updated_by,
        }


def set_scope_policy(
    scope_key: str, creation_policy: str, updated_by: str = "", max_concurrent: int = 0
) -> None:
    with ai_store.Session() as session:
        row = session.get(AIScopeTaskPolicy, scope_key)
        if row is None:
            session.add(
                AIScopeTaskPolicy(
                    scope_key=scope_key,
                    creation_policy=creation_policy,
                    max_concurrent=max_concurrent,
                    updated_by=updated_by,
                )
            )
        else:
            row.creation_policy = creation_policy
            row.max_concurrent = max_concurrent
            row.updated_by = updated_by
            row.updated_at = _now()
        session.commit()


# ------------------------------------------------------------ Workspace


def _ws_to_dict(row: AIScopeTaskWorkspace) -> dict[str, Any]:
    return {
        "id": row.id,
        "scope_key": row.scope_key,
        "name": row.name,
        "root": row.root,
        "mode": row.mode,
        "is_default": row.is_default,
    }


def list_workspaces(scope_key: str) -> list[dict[str, Any]]:
    with ai_store.Session() as session:
        stmt = (
            select(AIScopeTaskWorkspace)
            .where(AIScopeTaskWorkspace.scope_key == scope_key)
            .order_by(AIScopeTaskWorkspace.name)
        )
        return [_ws_to_dict(r) for r in session.execute(stmt).scalars().all()]


def get_workspace(scope_key: str, name: str) -> dict[str, Any] | None:
    with ai_store.Session() as session:
        stmt = select(AIScopeTaskWorkspace).where(
            AIScopeTaskWorkspace.scope_key == scope_key,
            AIScopeTaskWorkspace.name == name,
        )
        row = session.execute(stmt).scalars().first()
        return _ws_to_dict(row) if row is not None else None


def add_workspace(
    scope_key: str, name: str, root: str, mode: str, updated_by: str = ""
) -> str:
    """新增 workspace；返回状态文案（空表示成功）。重复名返回提示。"""
    with ai_store.Session() as session:
        existing = (
            session.execute(
                select(AIScopeTaskWorkspace).where(
                    AIScopeTaskWorkspace.scope_key == scope_key,
                    AIScopeTaskWorkspace.name == name,
                )
            )
            .scalars()
            .first()
        )
        if existing is not None:
            return f"workspace `{name}` 已存在。"
        session.add(
            AIScopeTaskWorkspace(
                scope_key=scope_key,
                name=name,
                root=root,
                mode=mode,
                updated_by=updated_by,
            )
        )
        session.commit()
        return ""


def remove_workspace(scope_key: str, name: str) -> bool:
    with ai_store.Session() as session:
        stmt = select(AIScopeTaskWorkspace).where(
            AIScopeTaskWorkspace.scope_key == scope_key,
            AIScopeTaskWorkspace.name == name,
        )
        row = session.execute(stmt).scalars().first()
        if row is None:
            return False
        session.delete(row)
        session.commit()
        return True


def set_default_workspace(scope_key: str, name: str) -> bool:
    """把指定 workspace 设为 default（同 scope 唯一）。"""
    with ai_store.Session() as session:
        ws = (
            session.execute(
                select(AIScopeTaskWorkspace).where(
                    AIScopeTaskWorkspace.scope_key == scope_key,
                    AIScopeTaskWorkspace.name == name,
                )
            )
            .scalars()
            .first()
        )
        if ws is None:
            return False
        for other in (
            session.execute(
                select(AIScopeTaskWorkspace).where(
                    AIScopeTaskWorkspace.scope_key == scope_key
                )
            )
            .scalars()
            .all()
        ):
            other.is_default = other.id == ws.id
        session.commit()
        return True


def get_default_workspace(scope_key: str) -> dict[str, Any] | None:
    with ai_store.Session() as session:
        stmt = select(AIScopeTaskWorkspace).where(
            AIScopeTaskWorkspace.scope_key == scope_key,
            AIScopeTaskWorkspace.is_default.is_(True),
        )
        row = session.execute(stmt).scalars().first()
        return _ws_to_dict(row) if row is not None else None


# ------------------------------------------------------------ Snapshot


def get_capability_snapshot(task_id: str) -> dict[str, Any] | None:
    with ai_store.Session() as session:
        row = session.get(AITaskCapabilitySnapshot, task_id)
        if row is None:
            return None
        return {
            "task_id": row.task_id,
            "snapshot_json": row.snapshot_json,
            "schema_version": row.schema_version,
            "created_at": row.created_at,
        }
