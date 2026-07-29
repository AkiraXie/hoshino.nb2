"""Durable SQLite outbox for weibo post delivery.

Replaces the in-memory PostQueue for the dispatch phase, providing:
- Persistence across bot restarts (pending items survive)
- Retry with exponential backoff on send failure
- Deduplication via UNIQUE(group_id, uid, post_id)
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, TypeVar

from hoshino import db_dir
from hoshino.content import PostMessage

T = TypeVar("T")

MAX_ATTEMPTS = 8

# How long a dispatched item is leased before it may be picked up again. The
# dispatch job may run with overlapping instances (APScheduler max_instances=2),
# so due_outbox() claims items by pushing next_attempt_at this far ahead; a
# concurrent run then cannot re-read them. mark_sent/mark_failed/mark_dead
# finalize the item, and if the process dies mid-delivery the lease simply
# expires and the item becomes due again (no permanent "processing" limbo).
CLAIM_LEASE_SECONDS = 300.0


@dataclass(frozen=True, slots=True)
class WeiboOutboxItem:
    """A single pending weibo delivery read from the outbox."""

    id: int
    group_id: int
    target_data: str
    uid: str
    post_id: str
    post_payload: dict[str, Any]
    message_payload: dict[str, Any]
    attempts: int


def serialize_post_message(message: PostMessage) -> dict[str, Any]:
    """Serialize a PostMessage (with archived local paths) to a JSON-safe dict."""
    return {
        "text": message.text,
        "content": message.content,
        "screenshot": str(message.screenshot) if message.screenshot else None,
        "images": [str(p) for p in message.images],
        "videos": [str(p) for p in message.videos],
    }


def deserialize_post_message(data: dict[str, Any]) -> PostMessage:
    """Reconstruct a PostMessage from serialized dict."""
    screenshot = data.get("screenshot")
    return PostMessage(
        text=data.get("text", ""),
        content=data.get("content", ""),
        screenshot=Path(screenshot) if screenshot else None,
        images=[Path(p) for p in data.get("images", [])],
        videos=[Path(p) for p in data.get("videos", [])],
    )


def serialize_weibo_post(post: Any) -> dict[str, Any]:
    """Serialize a WeiboPost to a JSON-safe dict for outbox storage."""
    repost = None
    if post.repost is not None:
        repost = serialize_weibo_post(post.repost)
    return {
        "uid": post.uid,
        "id": post.id,
        "content": post.content,
        "title": getattr(post, "title", ""),
        "images": list(post.images),
        "videos": list(post.videos),
        "timestamp": post.timestamp,
        "url": post.url,
        "nickname": post.nickname,
        "description": getattr(post, "description", ""),
        "user_avatar_image": getattr(post, "user_avatar_image", ""),
        "repost": repost,
    }


class WeiboOutboxStore:
    """SQLite-backed durable delivery queue for weibo posts."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (db_dir / "weibo_outbox.db")
        self._lock = asyncio.Lock()
        self._initialized = False

    async def initialize(self) -> None:
        async with self._lock:
            if self._initialized:
                return
            await asyncio.to_thread(self._initialize_sync)
            self._initialized = True

    async def enqueue(
        self,
        *,
        group_id: int,
        target_data: str,
        uid: str,
        post_id: str,
        post_payload: dict[str, Any],
        message_payload: dict[str, Any],
    ) -> bool:
        """Insert a delivery item. Returns False if already exists (dedup)."""
        now = time.time()

        def operation(conn: sqlite3.Connection) -> bool:
            result = conn.execute(
                """
                INSERT OR IGNORE INTO weibo_outbox(
                    group_id, target_data, uid, post_id,
                    post_payload, message_payload,
                    status, attempts, next_attempt_at, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'pending', 0, ?, ?)
                """,
                (
                    group_id,
                    target_data,
                    uid,
                    post_id,
                    json.dumps(post_payload, ensure_ascii=False),
                    json.dumps(message_payload, ensure_ascii=False),
                    now,
                    now,
                ),
            )
            return result.rowcount > 0

        return await self._transaction(operation)

    async def due_outbox(self, limit: int = 10) -> list[WeiboOutboxItem]:
        """Claim and return up to *limit* pending items whose retry time passed.

        Claiming bumps ``next_attempt_at`` ahead by the lease within the same
        transaction, so overlapping dispatch runs cannot pick the same item and
        deliver it twice.
        """
        now = time.time()
        claim_until = now + CLAIM_LEASE_SECONDS

        def operation(conn: sqlite3.Connection) -> list[WeiboOutboxItem]:
            rows = conn.execute(
                """
                SELECT * FROM weibo_outbox
                WHERE status = 'pending' AND next_attempt_at <= ?
                ORDER BY id
                LIMIT ?
                """,
                (now, max(1, limit)),
            ).fetchall()
            if rows:
                ids = [int(row["id"]) for row in rows]
                placeholders = ",".join("?" * len(ids))
                conn.execute(
                    f"UPDATE weibo_outbox SET next_attempt_at = ? WHERE id IN ({placeholders})",
                    (claim_until, *ids),
                )
            return [
                WeiboOutboxItem(
                    id=int(row["id"]),
                    group_id=int(row["group_id"]),
                    target_data=str(row["target_data"]),
                    uid=str(row["uid"]),
                    post_id=str(row["post_id"]),
                    post_payload=json.loads(row["post_payload"]),
                    message_payload=json.loads(row["message_payload"]),
                    attempts=int(row["attempts"]),
                )
                for row in rows
            ]

        return await self._transaction(operation)

    async def mark_sent(self, item_id: int) -> None:
        await self._execute(
            "UPDATE weibo_outbox SET status = 'sent', sent_at = ?, last_error = NULL WHERE id = ?",
            (time.time(), item_id),
        )

    async def mark_failed(self, item_id: int, retry_at: float, error: str) -> None:
        await self._execute(
            """
            UPDATE weibo_outbox
            SET attempts = attempts + 1, next_attempt_at = ?, last_error = ?
            WHERE id = ?
            """,
            (retry_at, error[:1000], item_id),
        )

    async def mark_dead(self, item_id: int, error: str) -> None:
        """Mark an item as permanently failed (exceeded max attempts)."""
        await self._execute(
            "UPDATE weibo_outbox SET status = 'dead', last_error = ? WHERE id = ?",
            (error[:1000], item_id),
        )

    async def pending_count(self) -> int:
        return await self._read(
            lambda conn: conn.execute(
                "SELECT COUNT(*) FROM weibo_outbox WHERE status = 'pending'"
            ).fetchone()[0]
        )

    async def cleanup_old(self, days: int = 7) -> int:
        """Remove sent/dead items older than *days*."""
        cutoff = time.time() - days * 86400

        def operation(conn: sqlite3.Connection) -> int:
            return conn.execute(
                "DELETE FROM weibo_outbox WHERE status IN ('sent', 'dead') AND created_at < ?",
                (cutoff,),
            ).rowcount

        return await self._transaction(operation)

    # ── internal ──────────────────────────────────────────

    async def _transaction(self, operation: Callable[[sqlite3.Connection], T]) -> T:
        await self.initialize()
        async with self._lock:
            return await asyncio.to_thread(self._transaction_sync, operation)

    async def _read(self, operation: Callable[[sqlite3.Connection], T]) -> T:
        await self.initialize()
        async with self._lock:
            return await asyncio.to_thread(self._read_sync, operation)

    async def _execute(self, sql: str, params: tuple[Any, ...]) -> None:
        await self._transaction(lambda conn: conn.execute(sql, params))

    def _initialize_sync(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(
                """
                PRAGMA journal_mode = WAL;
                CREATE TABLE IF NOT EXISTS weibo_outbox (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    group_id INTEGER NOT NULL,
                    target_data TEXT NOT NULL DEFAULT '',
                    uid TEXT NOT NULL,
                    post_id TEXT NOT NULL,
                    post_payload TEXT NOT NULL,
                    message_payload TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    attempts INTEGER NOT NULL DEFAULT 0,
                    next_attempt_at REAL NOT NULL,
                    last_error TEXT,
                    created_at REAL NOT NULL,
                    sent_at REAL,
                    UNIQUE(group_id, uid, post_id)
                );
                CREATE INDEX IF NOT EXISTS weibo_outbox_due_idx
                    ON weibo_outbox(status, next_attempt_at);
                """
            )

    def _transaction_sync(self, operation: Callable[[sqlite3.Connection], T]) -> T:
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                result = operation(conn)
            except Exception:
                conn.rollback()
                raise
            conn.commit()
            return result

    def _read_sync(self, operation: Callable[[sqlite3.Connection], T]) -> T:
        with self._connect() as conn:
            return operation(conn)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout = 30000")
        return conn


__all__ = [
    "MAX_ATTEMPTS",
    "WeiboOutboxItem",
    "WeiboOutboxStore",
    "deserialize_post_message",
    "serialize_post_message",
    "serialize_weibo_post",
]
