"""AI 模块 SQLite 持久化：会话历史、scope provider、用量事件。

沿用仓库现有同步 SQLAlchemy 模式（``DeclarativeBase`` + ``sessionmaker`` +
``on_serial_startup`` 建表）。数据库位于 ``data/db/aichat.db``。

``messages_json`` 存原始 JSON 字符串；会话消息的序列化/反序列化由
``context.py``（Pydantic AI ``ModelMessagesTypeAdapter``）负责，store 保持无
pydantic-ai 依赖，便于独立测试。
"""

from __future__ import annotations

import json
import os
import time
import uuid
from typing import Any

from sqlalchemy import (
    UniqueConstraint,
    case,
    create_engine,
    delete,
    func,
    select,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from sqlalchemy.types import Boolean, Float, Integer, Text

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
    _migrate_missing_columns(engine)
    migrate_sessions_to_conversations(engine)


def _migrate_missing_columns(target_engine) -> None:
    """create_all 不会给已存在的表补列：对旧库幂等补齐后续新增的列。"""
    with target_engine.connect() as conn:
        cols = {
            row[1]
            for row in conn.exec_driver_sql("PRAGMA table_info(ai_tasks)").fetchall()
        }
        if cols and "adapter_name" not in cols:
            conn.exec_driver_sql(
                "ALTER TABLE ai_tasks ADD COLUMN adapter_name TEXT NOT NULL DEFAULT ''"
            )
            conn.commit()


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
    """删除 scope 会话历史；返回是否真的删除了记录。

    已废弃：多对话模型用 ``clear_conversation_events``；保留供旧命令过渡。
    """
    with Session() as session:
        obj = session.get(AISession, scope_key)
        if obj is None:
            return False
        session.delete(obj)
        session.commit()
        return True


# ------------------------------------------------------------- conversations
#
# Session(scope) → Conversation 双层模型（plan aichat-context-timeout，
# 对齐 AstrBot ConversationManager）：一个 scope 持有多个命名对话，
# ``ai_scope_chat_states`` 记录当前激活对话；历史仍是 pydantic-ai messages JSON。
# ``ai_sessions`` 被取代：启动时幂等迁移为每个 scope 的「默认」对话。


class AIConversation(Base):
    """scope 内的一个命名对话（上下文线程）。"""

    __tablename__ = "ai_conversations"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    scope_key: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    messages_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    provider_id: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[float] = mapped_column(Float, nullable=False, default=time.time)
    updated_at: Mapped[float] = mapped_column(Float, nullable=False, default=time.time)

    __table_args__ = (
        # scope 内对话名唯一（名称即切换命令的寻址键）。
        UniqueConstraint("scope_key", "name", name="uq_conv_scope_name"),
    )


class AIScopeChatState(Base):
    """scope 的聊天指针：当前激活对话 + LRU 辅助信息。"""

    __tablename__ = "ai_scope_chat_states"

    scope_key: Mapped[str] = mapped_column(Text, primary_key=True)
    active_conv_id: Mapped[str] = mapped_column(Text, nullable=False, default="")
    updated_at: Mapped[float] = mapped_column(Float, nullable=False, default=time.time)


class AIConversationEvent(Base):
    """append-only 对话事件日志：模型历史由事件派生（可恢复、可重放）。

    ``seq`` 在单个对话内从 0 单调连续（由写方保证，SQLite 不校验）；``type``
    为 surface 事件名（见 ``_context``），``data_json`` 为其 payload（JSON）。
    只追加、不更新；``clear`` 走整段删除。
    """

    __tablename__ = "ai_conversation_events"

    conv_id: Mapped[str] = mapped_column(Text, primary_key=True)
    seq: Mapped[int] = mapped_column(Integer, primary_key=True)
    time: Mapped[float] = mapped_column(Float, nullable=False, default=time.time)
    type: Mapped[str] = mapped_column(Text, nullable=False)
    data_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")


def new_conversation_id() -> str:
    return f"c_{uuid.uuid4().hex[:12]}"


def migrate_sessions_to_conversations(target_engine) -> None:
    """把旧 ``ai_sessions`` 单会话数据迁为「默认」对话（幂等）。

    scope 已有任何对话记录则跳过；旧表保留只读不删除。
    """
    SessionLocal = sessionmaker(bind=target_engine, expire_on_commit=False)
    with SessionLocal() as session:
        existing_scopes = set(
            session.execute(select(AIConversation.scope_key).distinct()).scalars().all()
        )
        now = time.time()
        for legacy in session.execute(select(AISession)).scalars():
            if legacy.scope_key in existing_scopes:
                continue
            conv_id = new_conversation_id()
            session.add(
                AIConversation(
                    id=conv_id,
                    scope_key=legacy.scope_key,
                    name="默认",
                    messages_json=legacy.messages_json or "[]",
                    provider_id=legacy.provider_id or "",
                    created_at=legacy.created_at,
                    updated_at=legacy.updated_at,
                )
            )
            session.add(
                AIScopeChatState(
                    scope_key=legacy.scope_key, active_conv_id=conv_id, updated_at=now
                )
            )
            existing_scopes.add(legacy.scope_key)
        session.commit()


def create_conversation(
    scope_key: str, conv_id: str, name: str, provider_id: str = ""
) -> None:
    now = time.time()
    with Session() as session:
        session.add(
            AIConversation(
                id=conv_id,
                scope_key=scope_key,
                name=name,
                provider_id=provider_id,
                created_at=now,
                updated_at=now,
            )
        )
        session.commit()


def get_conversation(conv_id: str) -> dict | None:
    with Session() as session:
        row = session.get(AIConversation, conv_id)
        return _conversation_to_dict(row) if row is not None else None


def get_conversations(scope_key: str) -> list[dict]:
    """scope 的全部对话，按更新时间倒序（最近用过的在前）。"""
    with Session() as session:
        rows = (
            session.execute(
                select(AIConversation)
                .where(AIConversation.scope_key == scope_key)
                .order_by(AIConversation.updated_at.desc())
            )
            .scalars()
            .all()
        )
        return [_conversation_to_dict(r) for r in rows]


def find_conversation_by_name(scope_key: str, name: str) -> dict | None:
    with Session() as session:
        row = (
            session.execute(
                select(AIConversation).where(
                    AIConversation.scope_key == scope_key,
                    AIConversation.name == name,
                )
            )
            .scalars()
            .first()
        )
        return _conversation_to_dict(row) if row is not None else None


def save_conversation_messages(
    conv_id: str, messages_json: str, provider_id: str = ""
) -> None:
    now = time.time()
    with Session() as session:
        row = session.get(AIConversation, conv_id)
        if row is None:
            return
        row.messages_json = messages_json
        if provider_id:
            row.provider_id = provider_id
        row.updated_at = now
        session.commit()


def clear_conversation_messages(conv_id: str) -> bool:
    with Session() as session:
        row = session.get(AIConversation, conv_id)
        if row is None:
            return False
        row.messages_json = "[]"
        row.updated_at = time.time()
        session.commit()
        return True


def get_active_conv_id(scope_key: str) -> str | None:
    with Session() as session:
        row = session.get(AIScopeChatState, scope_key)
        return row.active_conv_id if row is not None else None


def set_active_conv_id(scope_key: str, conv_id: str) -> None:
    now = time.time()
    with Session() as session:
        row = session.get(AIScopeChatState, scope_key)
        if row is None:
            session.add(
                AIScopeChatState(
                    scope_key=scope_key, active_conv_id=conv_id, updated_at=now
                )
            )
        else:
            row.active_conv_id = conv_id
            row.updated_at = now
        session.commit()


def _conversation_to_dict(row: AIConversation) -> dict:
    return {
        "id": row.id,
        "scope_key": row.scope_key,
        "name": row.name,
        "messages_json": row.messages_json,
        "provider_id": row.provider_id,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


# ------------------------------------------------------------- conversation events


def _event_to_dict(row: AIConversationEvent) -> dict:
    return {
        "seq": row.seq,
        "time": row.time,
        "type": row.type,
        "data": json.loads(row.data_json) if row.data_json else {},
    }


def append_conversation_events(conv_id: str, events: list[dict]) -> None:
    """批量 append 事件到对话日志（seq 按现有最大 +1 递增）。

    同时刷新 ``ai_conversations.updated_at``。事件 dict 为 ``{type, data}``，
    seq/time 由本函数填充。
    """
    if not events:
        return
    now = time.time()
    with Session() as session:
        row = session.get(AIConversation, conv_id)
        if row is None:
            return
        max_seq = (
            session.execute(
                select(func.max(AIConversationEvent.seq)).where(
                    AIConversationEvent.conv_id == conv_id
                )
            ).scalar()
            or -1
        )
        seq = max_seq + 1
        for event in events:
            session.add(
                AIConversationEvent(
                    conv_id=conv_id,
                    seq=seq,
                    time=now,
                    type=event["type"],
                    data_json=json.dumps(event["data"], ensure_ascii=False),
                )
            )
            seq += 1
        row.updated_at = now
        session.commit()


def load_conversation_events(conv_id: str, *, after_seq: int = -1) -> list[dict]:
    """按 seq 升序读事件；``after_seq`` 支持增量读（-1 读全部）。"""
    with Session() as session:
        rows = (
            session.execute(
                select(AIConversationEvent)
                .where(
                    AIConversationEvent.conv_id == conv_id,
                    AIConversationEvent.seq > after_seq,
                )
                .order_by(AIConversationEvent.seq)
            )
            .scalars()
            .all()
        )
        return [_event_to_dict(row) for row in rows]


def count_conversation_events(
    conv_id: str, *, types: tuple[str, ...] | None = None
) -> int:
    """对话事件条数；``types`` 非空时只数指定类型（如 surface 事件）。"""
    with Session() as session:
        stmt = select(func.count(AIConversationEvent.seq)).where(
            AIConversationEvent.conv_id == conv_id
        )
        if types is not None:
            stmt = stmt.where(AIConversationEvent.type.in_(types))
        return session.execute(stmt).scalar() or 0


def migrate_conv_events_if_empty(conv_id: str, events: list[dict]) -> bool:
    """仅当对话尚无事件时批量写入（幂等、原子，规避并发双写）。

    供加载期把旧 ``messages_json`` 惰性迁移为事件；已迁移则返回 False。
    """
    if not events:
        return False
    now = time.time()
    with Session() as session:
        has = (
            session.execute(
                select(AIConversationEvent.conv_id)
                .where(AIConversationEvent.conv_id == conv_id)
                .limit(1)
            ).first()
            is not None
        )
        if has:
            return False
        for idx, event in enumerate(events):
            session.add(
                AIConversationEvent(
                    conv_id=conv_id,
                    seq=idx,
                    time=now,
                    type=event["type"],
                    data_json=json.dumps(event["data"], ensure_ascii=False),
                )
            )
        session.commit()
        return True


def clear_conversation_events(conv_id: str) -> bool:
    """删除对话全部事件并清空旧 messages_json 列；返回是否有记录。"""
    with Session() as session:
        row = session.get(AIConversation, conv_id)
        if row is None:
            return False
        session.execute(
            delete(AIConversationEvent).where(AIConversationEvent.conv_id == conv_id)
        )
        row.messages_json = "[]"
        row.updated_at = time.time()
        session.commit()
        return True


def update_conversation_provider(conv_id: str, provider_id: str) -> None:
    """仅更新对话最近 provider（不触碰事件日志）。"""
    if not provider_id:
        return
    now = time.time()
    with Session() as session:
        row = session.get(AIConversation, conv_id)
        if row is None:
            return
        row.provider_id = provider_id
        row.updated_at = now
        session.commit()


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


# ------------------------------------------------------------ tool bindings


class AIScopeToolBinding(Base):
    """scope 的工具类别绑定。category 是授权粒度；无行时使用安全默认。"""

    __tablename__ = "ai_scope_tool_bindings"

    scope_key: Mapped[str] = mapped_column(Text, primary_key=True)
    category: Mapped[str] = mapped_column(Text, primary_key=True)
    surface: Mapped[str] = mapped_column(Text, primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    updated_by: Mapped[str] = mapped_column(Text, nullable=False, default="")
    updated_at: Mapped[float] = mapped_column(Float, nullable=False, default=time.time)


def set_scope_tool_binding(
    scope_key: str,
    category: str,
    surface: str,
    enabled: bool,
    updated_by: str = "",
) -> None:
    """更新 scope 的工具类别绑定（upsert）。"""
    now = time.time()
    with Session() as session:
        obj = session.get(AIScopeToolBinding, (scope_key, category, surface))
        if obj is None:
            session.add(
                AIScopeToolBinding(
                    scope_key=scope_key,
                    category=category,
                    surface=surface,
                    enabled=enabled,
                    updated_by=updated_by,
                    updated_at=now,
                )
            )
        else:
            obj.enabled = enabled
            obj.updated_by = updated_by
            obj.updated_at = now
        session.commit()


def get_scope_tool_bindings(scope_key: str, surface: str) -> set[str]:
    """返回 scope 在指定 surface 上已启用的工具类别集合。

    安全默认：无行时返回空集（``computer``/``bot`` 默认不注入）。
    """
    with Session() as session:
        stmt = select(AIScopeToolBinding).where(
            AIScopeToolBinding.scope_key == scope_key,
            AIScopeToolBinding.surface == surface,
            AIScopeToolBinding.enabled.is_(True),
        )
        return {row.category for row in session.execute(stmt).scalars().all()}


def list_scope_tool_bindings(scope_key: str, surface: str) -> list[dict[str, Any]]:
    """列出 scope 在指定 surface 上的全部绑定行（含关闭项），供管理命令展示。"""
    with Session() as session:
        stmt = (
            select(AIScopeToolBinding)
            .where(
                AIScopeToolBinding.scope_key == scope_key,
                AIScopeToolBinding.surface == surface,
            )
            .order_by(AIScopeToolBinding.category)
        )
        return [
            {
                "category": row.category,
                "enabled": row.enabled,
                "updated_by": row.updated_by,
                "updated_at": row.updated_at,
            }
            for row in session.execute(stmt).scalars().all()
        ]


# ----------------------------------------------------------------- personas


class AIPersona(Base):
    """命名 persona。prompt 由特征模板生成，也可手动覆盖。"""

    __tablename__ = "ai_personas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    gender: Mapped[str] = mapped_column(Text, nullable=False, default="")
    personality: Mapped[str] = mapped_column(Text, nullable=False, default="")
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    prompt: Mapped[str] = mapped_column(Text, nullable=False, default="")
    traits_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_by: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[float] = mapped_column(Float, nullable=False, default=time.time)
    updated_at: Mapped[float] = mapped_column(Float, nullable=False, default=time.time)


class AIScopePersona(Base):
    """scope 级 persona 绑定（scope_key 唯一）。"""

    __tablename__ = "ai_scope_personas"

    scope_key: Mapped[str] = mapped_column(Text, primary_key=True)
    persona_id: Mapped[int] = mapped_column(Integer, nullable=False)
    updated_by: Mapped[str] = mapped_column(Text, nullable=False, default="")
    updated_at: Mapped[float] = mapped_column(Float, nullable=False, default=time.time)


class AIGlobal(Base):
    """全局键值（persona 全局绑定用 key='global_persona'）。"""

    __tablename__ = "ai_globals"

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False, default="")


def _persona_to_dict(row: AIPersona) -> dict[str, Any]:
    return {
        "id": row.id,
        "name": row.name,
        "gender": row.gender,
        "personality": row.personality,
        "description": row.description,
        "prompt": row.prompt,
        "traits_json": row.traits_json,
        "created_by": row.created_by,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def list_personas() -> list[dict[str, Any]]:
    with Session() as session:
        stmt = select(AIPersona).order_by(AIPersona.name)
        return [_persona_to_dict(row) for row in session.execute(stmt).scalars().all()]


def get_persona_by_name(name: str) -> dict[str, Any] | None:
    with Session() as session:
        row = session.execute(
            select(AIPersona).where(AIPersona.name == name)
        ).scalar_one_or_none()
        return _persona_to_dict(row) if row is not None else None


def get_persona_by_id(persona_id: int) -> dict[str, Any] | None:
    with Session() as session:
        row = session.get(AIPersona, persona_id)
        return _persona_to_dict(row) if row is not None else None


def create_persona(
    *,
    name: str,
    gender: str = "",
    personality: str = "",
    description: str = "",
    prompt: str = "",
    traits_json: str = "{}",
    created_by: str = "",
) -> dict[str, Any]:
    """创建 persona；prompt 为空时由调用方（persona.py）生成模板。"""
    with Session() as session:
        row = AIPersona(
            name=name,
            gender=gender,
            personality=personality,
            description=description,
            prompt=prompt,
            traits_json=traits_json,
            created_by=created_by,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return _persona_to_dict(row)


def update_persona(
    name: str,
    *,
    gender: str | None = None,
    personality: str | None = None,
    description: str | None = None,
    prompt: str | None = None,
    traits_json: str | None = None,
) -> dict[str, Any] | None:
    """更新 persona 特征并刷新 prompt；不存在返回 None。"""
    with Session() as session:
        row = session.execute(
            select(AIPersona).where(AIPersona.name == name)
        ).scalar_one_or_none()
        if row is None:
            return None
        if gender is not None:
            row.gender = gender
        if personality is not None:
            row.personality = personality
        if description is not None:
            row.description = description
        if prompt is not None:
            row.prompt = prompt
        if traits_json is not None:
            row.traits_json = traits_json
        row.updated_at = time.time()
        session.commit()
        return _persona_to_dict(row)


def delete_persona(name: str) -> bool:
    """删除 persona 及绑定引用；返回是否删除了记录。"""
    with Session() as session:
        row = session.execute(
            select(AIPersona).where(AIPersona.name == name)
        ).scalar_one_or_none()
        if row is None:
            return False
        persona_id = row.id
        # 清理 scope / global 绑定引用
        session.execute(
            AIScopePersona.__table__.delete().where(
                AIScopePersona.persona_id == persona_id
            )
        )
        session.execute(
            AIGlobal.__table__.delete().where(
                AIGlobal.key == "global_persona", AIGlobal.value == name
            )
        )
        session.delete(row)
        session.commit()
        return True


def bind_scope_persona(scope_key: str, persona_id: int, updated_by: str = "") -> None:
    """绑定 scope 级 persona（upsert）。"""
    with Session() as session:
        row = session.get(AIScopePersona, scope_key)
        if row is None:
            session.add(
                AIScopePersona(
                    scope_key=scope_key,
                    persona_id=persona_id,
                    updated_by=updated_by,
                )
            )
        else:
            row.persona_id = persona_id
            row.updated_by = updated_by
            row.updated_at = time.time()
        session.commit()


def get_scope_persona_id(scope_key: str) -> int | None:
    with Session() as session:
        row = session.get(AIScopePersona, scope_key)
        return row.persona_id if row is not None else None


def clear_scope_persona(scope_key: str) -> bool:
    with Session() as session:
        row = session.get(AIScopePersona, scope_key)
        if row is None:
            return False
        session.delete(row)
        session.commit()
        return True


def get_global_value(key: str) -> str | None:
    with Session() as session:
        row = session.get(AIGlobal, key)
        return row.value if row is not None else None


def set_global_value(key: str, value: str) -> None:
    with Session() as session:
        row = session.get(AIGlobal, key)
        if row is None:
            session.add(AIGlobal(key=key, value=value))
        else:
            row.value = value
        session.commit()


def clear_global_value(key: str) -> bool:
    with Session() as session:
        row = session.get(AIGlobal, key)
        if row is None:
            return False
        session.delete(row)
        session.commit()
        return True


# ------------------------------------------------------------------- memory


class AIMemory(Base):
    """scope 隔离的长期记忆。"""

    __tablename__ = "ai_memory"

    scope_key: Mapped[str] = mapped_column(Text, primary_key=True)
    key: Mapped[str] = mapped_column(Text, primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False, default="")
    updated_at: Mapped[float] = mapped_column(Float, nullable=False, default=time.time)


def memory_get(scope_key: str, key: str) -> str | None:
    with Session() as session:
        row = session.get(AIMemory, (scope_key, key))
        return row.value if row is not None else None


def memory_set(scope_key: str, key: str, value: str) -> None:
    """写入长期记忆（upsert）。值长度限制由调用方（memory 工具）负责。"""
    with Session() as session:
        row = session.get(AIMemory, (scope_key, key))
        if row is None:
            session.add(AIMemory(scope_key=scope_key, key=key, value=value))
        else:
            row.value = value
            row.updated_at = time.time()
        session.commit()


def memory_delete(scope_key: str, key: str) -> bool:
    with Session() as session:
        row = session.get(AIMemory, (scope_key, key))
        if row is None:
            return False
        session.delete(row)
        session.commit()
        return True


def memory_list_keys(scope_key: str) -> list[str]:
    with Session() as session:
        stmt = (
            select(AIMemory.key)
            .where(AIMemory.scope_key == scope_key)
            .order_by(AIMemory.key)
        )
        return list(session.execute(stmt).scalars().all())


# ------------------------------------------------------------- skill states


class AISkillState(Base):
    """scope 对技能的启停状态；无行默认 enabled=True。"""

    __tablename__ = "ai_skill_states"

    scope_key: Mapped[str] = mapped_column(Text, primary_key=True)
    skill_name: Mapped[str] = mapped_column(Text, primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    updated_at: Mapped[float] = mapped_column(Float, nullable=False, default=time.time)


def get_skill_enabled(scope_key: str, skill_name: str) -> bool:
    with Session() as session:
        row = session.get(AISkillState, (scope_key, skill_name))
        return row.enabled if row is not None else True


def set_skill_enabled(scope_key: str, skill_name: str, enabled: bool) -> None:
    """更新技能启停（upsert）。"""
    with Session() as session:
        row = session.get(AISkillState, (scope_key, skill_name))
        if row is None:
            session.add(
                AISkillState(
                    scope_key=scope_key,
                    skill_name=skill_name,
                    enabled=enabled,
                )
            )
        else:
            row.enabled = enabled
            row.updated_at = time.time()
        session.commit()


# ------------------------------------------------------------- goals


class AIGoal(Base):
    """每 scope 一个跨轮持续目标（GoalService 状态行，revision CAS）。"""

    __tablename__ = "ai_goals"

    scope_key: Mapped[str] = mapped_column(Text, primary_key=True)
    objective: Mapped[str] = mapped_column(Text, nullable=False, default="")
    phase: Mapped[str] = mapped_column(Text, nullable=False, default="active")
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    max_rounds: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)
    completed_rounds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    blocked_reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[float] = mapped_column(Float, nullable=False, default=time.time)
    updated_at: Mapped[float] = mapped_column(Float, nullable=False, default=time.time)


def _goal_to_dict(row: AIGoal) -> dict:
    return {
        "scope_key": row.scope_key,
        "objective": row.objective,
        "phase": row.phase,
        "revision": row.revision,
        "max_rounds": row.max_rounds,
        "completed_rounds": row.completed_rounds,
        "blocked_reason": row.blocked_reason,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def get_goal(scope_key: str) -> dict | None:
    with Session() as session:
        row = session.get(AIGoal, scope_key)
        return _goal_to_dict(row) if row is not None else None


def upsert_goal(
    scope_key: str,
    *,
    objective: str,
    phase: str,
    revision: int,
    max_rounds: int | None = None,
    completed_rounds: int = 0,
    blocked_reason: str = "",
) -> None:
    """写入/更新目标状态（revision CAS 由 GoalService 保证，这里只落库）。"""
    now = time.time()
    with Session() as session:
        row = session.get(AIGoal, scope_key)
        if row is None:
            session.add(
                AIGoal(
                    scope_key=scope_key,
                    objective=objective,
                    phase=phase,
                    revision=revision,
                    max_rounds=max_rounds,
                    completed_rounds=completed_rounds,
                    blocked_reason=blocked_reason,
                    created_at=now,
                    updated_at=now,
                )
            )
        else:
            row.objective = objective
            row.phase = phase
            row.revision = revision
            row.max_rounds = max_rounds
            row.completed_rounds = completed_rounds
            row.blocked_reason = blocked_reason
            row.updated_at = now
        session.commit()


def delete_goal(scope_key: str) -> bool:
    with Session() as session:
        row = session.get(AIGoal, scope_key)
        if row is None:
            return False
        session.delete(row)
        session.commit()
        return True
