"""AI 模块 SQLite 持久化：会话历史、scope provider、用量事件。

沿用仓库现有同步 SQLAlchemy 模式（``DeclarativeBase`` + ``sessionmaker`` +
``on_serial_startup`` 建表）。数据库位于 ``data/db/aichat.db``。

``messages_json`` 存原始 JSON 字符串；会话消息的序列化/反序列化由
``context.py``（Pydantic AI ``ModelMessagesTypeAdapter``）负责，store 保持无
pydantic-ai 依赖，便于独立测试。
"""

from __future__ import annotations

import os
import time
from typing import Any

from sqlalchemy import (
    case,
    create_engine,
    func,
    select,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from sqlalchemy.types import Float, Integer, Text

from hoshino import db_dir
from hoshino.core.hooks import on_serial_startup

db_path = os.path.join(db_dir, "aichat.db")
engine = create_engine(f"sqlite:///{db_path}", echo=False, future=True)
Session = sessionmaker(bind=engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class AISession(Base):
    """scope 会话历史。scope_key 用 ``event_scope_key``，区分群/私聊与 adapter。"""

    __tablename__ = "ai_sessions"

    scope_key: Mapped[str] = mapped_column(Text, primary_key=True)
    provider_id: Mapped[str] = mapped_column(Text, nullable=False, default="")
    messages_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    updated_at: Mapped[float] = mapped_column(Float, nullable=False, default=time.time)
    created_at: Mapped[float] = mapped_column(Float, nullable=False, default=time.time)


class AIScopeProvider(Base):
    """scope 绑定的 provider。provider_id 必须存在于 AIConfig.providers。"""

    __tablename__ = "ai_scope_providers"

    scope_key: Mapped[str] = mapped_column(Text, primary_key=True)
    provider_id: Mapped[str] = mapped_column(Text, nullable=False, default="")
    updated_by: Mapped[str] = mapped_column(Text, nullable=False, default="")
    updated_at: Mapped[float] = mapped_column(Float, nullable=False, default=time.time)


class AIUsageEvent(Base):
    """append-only 用量事件，成功与失败请求都记录。"""

    __tablename__ = "ai_usage_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[float] = mapped_column(Float, nullable=False, default=time.time)
    provider_id: Mapped[str] = mapped_column(Text, nullable=False, default="")
    scope_key: Mapped[str] = mapped_column(Text, nullable=False, default="")
    model: Mapped[str] = mapped_column(Text, nullable=False, default="")
    request_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    response_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cache_read_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cache_write_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    latency_ms: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)


def ensure_schema() -> None:
    Base.metadata.create_all(engine)


@on_serial_startup
async def _ensure_ai_schema() -> None:
    ensure_schema()


# ---------------------------------------------------------------- sessions


def save_session_messages(
    scope_key: str,
    messages_json: str,
    provider_id: str = "",
) -> None:
    """写入 scope 会话历史。messages_json 为序列化后的 JSON 字符串。"""
    now = time.time()
    with Session() as session:
        obj = session.get(AISession, scope_key)
        if obj is None:
            obj = AISession(
                scope_key=scope_key,
                provider_id=provider_id,
                messages_json=messages_json,
                created_at=now,
            )
            session.add(obj)
        else:
            obj.messages_json = messages_json
            obj.provider_id = provider_id or obj.provider_id
            obj.updated_at = now
        session.commit()


def load_session_messages(scope_key: str) -> str | None:
    """读取 scope 会话历史 JSON；不存在返回 None。"""
    with Session() as session:
        obj = session.get(AISession, scope_key)
        return obj.messages_json if obj is not None else None


def get_session_provider(scope_key: str) -> str | None:
    """读取会话最近一次使用的 provider_id。"""
    with Session() as session:
        obj = session.get(AISession, scope_key)
        return obj.provider_id if obj is not None else None


def clear_session(scope_key: str) -> bool:
    """删除 scope 会话历史；返回是否真的删除了记录。"""
    with Session() as session:
        obj = session.get(AISession, scope_key)
        if obj is None:
            return False
        session.delete(obj)
        session.commit()
        return True


# ------------------------------------------------------------- scope providers


def get_scope_provider(scope_key: str) -> str | None:
    with Session() as session:
        obj = session.get(AIScopeProvider, scope_key)
        return obj.provider_id if obj is not None else None


def set_scope_provider(scope_key: str, provider_id: str, updated_by: str = "") -> None:
    now = time.time()
    with Session() as session:
        obj = session.get(AIScopeProvider, scope_key)
        if obj is None:
            obj = AIScopeProvider(
                scope_key=scope_key,
                provider_id=provider_id,
                updated_by=updated_by,
            )
            session.add(obj)
        else:
            obj.provider_id = provider_id
            obj.updated_by = updated_by
            obj.updated_at = now
        session.commit()


def clear_scope_provider(scope_key: str) -> bool:
    """清除 scope 的 provider 绑定；返回是否真的删除了记录。"""
    with Session() as session:
        obj = session.get(AIScopeProvider, scope_key)
        if obj is None:
            return False
        session.delete(obj)
        session.commit()
        return True


def clear_provider_references(provider_id: str) -> int:
    """删除 provider 前清理 scope 绑定表对该 provider 的引用；返回清理行数。"""
    with Session() as session:
        rows = (
            session.execute(
                select(AIScopeProvider).where(
                    AIScopeProvider.provider_id == provider_id
                )
            )
            .scalars()
            .all()
        )
        for row in rows:
            session.delete(row)
        session.commit()
        return len(rows)


# ----------------------------------------------------------------- usage events


def record_usage_event(
    *,
    provider_id: str,
    scope_key: str,
    model: str = "",
    request_tokens: int = 0,
    response_tokens: int = 0,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
    latency_ms: float = 0.0,
    error: str | None = None,
) -> None:
    """记录一次成功或失败的用量事件。"""
    with Session() as session:
        session.add(
            AIUsageEvent(
                ts=time.time(),
                provider_id=provider_id,
                scope_key=scope_key,
                model=model,
                request_tokens=request_tokens,
                response_tokens=response_tokens,
                total_tokens=request_tokens + response_tokens,
                cache_read_tokens=cache_read_tokens,
                cache_write_tokens=cache_write_tokens,
                latency_ms=latency_ms,
                error=error,
            )
        )
        session.commit()


def aggregate_usage(
    provider_id: str | None = None,
    since_ts: float | None = None,
) -> dict[str, Any]:
    """聚合用量指标。

    provider_id 为空时聚合全部 provider；since_ts 为空时统计全部时间。
    返回：事件数、总 token、平均延迟、缓存命中率、错误数等。
    """
    filters = []
    if provider_id:
        filters.append(AIUsageEvent.provider_id == provider_id)
    if since_ts is not None:
        filters.append(AIUsageEvent.ts >= since_ts)

    with Session() as session:
        stmt = select(
            func.count(AIUsageEvent.id),
            func.sum(AIUsageEvent.request_tokens),
            func.sum(AIUsageEvent.response_tokens),
            func.sum(AIUsageEvent.cache_read_tokens),
            func.sum(AIUsageEvent.cache_write_tokens),
            func.avg(AIUsageEvent.latency_ms),
            func.sum(case((AIUsageEvent.error.is_not(None), 1), else_=0)),
        )
        if filters:
            stmt = stmt.where(*filters)
        row = session.execute(stmt).one()
        request_tokens = row[1] or 0
        response_tokens = row[2] or 0
        cache_read = row[3] or 0
        cache_write = row[4] or 0
        latency = row[5] or 0.0
        error_count = row[6] or 0

        cache_denominator = cache_read + request_tokens
        hit_ratio = (cache_read / cache_denominator) if cache_denominator > 0 else 0.0
        return {
            "events": row[0] or 0,
            "request_tokens": request_tokens,
            "response_tokens": response_tokens,
            "total_tokens": request_tokens + response_tokens,
            "cache_read_tokens": cache_read,
            "cache_write_tokens": cache_write,
            "cache_hit_ratio": hit_ratio,
            "avg_latency_ms": latency,
            "error_count": error_count,
            "success_count": (row[0] or 0) - error_count,
        }
