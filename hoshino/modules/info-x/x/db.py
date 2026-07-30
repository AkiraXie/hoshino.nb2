"""Durable subscriptions, cursors, rate state, outbox and reaction mapping."""

from __future__ import annotations

import asyncio
import json
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, TypeVar

from hoshino import db_dir

from .post import XPost


T = TypeVar("T")

LIST_SOURCE_PREFIX = "list:"


def list_source_key(list_id: int) -> str:
    """Source key used to route a list through the user-oriented fetch machinery."""
    return f"{LIST_SOURCE_PREFIX}{int(list_id)}"


def parse_list_source_key(source: str) -> int | None:
    """Return the list id if ``source`` is a list source key, else None."""
    if not source.startswith(LIST_SOURCE_PREFIX):
        return None
    try:
        return int(source[len(LIST_SOURCE_PREFIX) :])
    except ValueError:
        return None


@dataclass(frozen=True, slots=True)
class Subscription:
    scope_key: str
    platform: str
    group_id: int
    target_data: str
    username: str
    name: str


@dataclass(frozen=True, slots=True)
class ListSubscription:
    scope_key: str
    platform: str
    group_id: int
    target_data: str
    list_id: int
    name: str


@dataclass(frozen=True, slots=True)
class AccountState:
    username: str
    user_id: int | None
    failures: int
    retry_at: float
    last_posted_at: float


@dataclass(frozen=True, slots=True)
class RatePermit:
    allowed: bool
    retry_at: float


@dataclass(frozen=True, slots=True)
class OutboxItem:
    id: int
    scope_key: str
    platform: str
    group_id: int
    target_data: str
    post: XPost
    attempts: int

    def get_id(self) -> str:
        return str(self.id)


class XStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (db_dir / "x.db")
        self._lock = asyncio.Lock()
        self._initialized = False

    async def initialize(self) -> None:
        async with self._lock:
            if self._initialized:
                return
            await asyncio.to_thread(self._initialize_sync)
            self._initialized = True

    async def add_subscription(
        self,
        *,
        scope_key: str,
        platform: str,
        group_id: int,
        target_data: str,
        username: str,
        name: str,
        cursor: int | None = None,
    ) -> bool:
        username = _username(username)

        def operation(conn: sqlite3.Connection) -> bool:
            result = conn.execute(
                """
                INSERT OR IGNORE INTO subscriptions(
                    scope_key, platform, group_id, target_data, username, name, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    scope_key,
                    platform,
                    group_id,
                    target_data,
                    username,
                    name,
                    time.time(),
                ),
            )
            conn.execute(
                """
                INSERT INTO account_state(username) VALUES (?)
                ON CONFLICT(username) DO NOTHING
                """,
                (username,),
            )
            if cursor is not None:
                self._upsert_cursor(conn, username, cursor)
            return result.rowcount > 0

        return await self._transaction(operation)

    async def remove_subscription(self, scope_key: str, username: str) -> bool:
        normalized = _username(username)

        def operation(conn: sqlite3.Connection) -> bool:
            deleted = conn.execute(
                "DELETE FROM subscriptions WHERE scope_key = ? AND username = ?",
                (scope_key, normalized),
            ).rowcount
            if deleted:
                # Keep the per-account invariant: once no subscription references
                # the username anymore, all of its derived state must go too, so an
                # orphaned outbox item cannot keep being delivered (and erroring).
                remaining = conn.execute(
                    "SELECT 1 FROM subscriptions WHERE username = ? LIMIT 1",
                    (normalized,),
                ).fetchone()
                if remaining is None:
                    self._purge_account_state(conn, normalized)
            return deleted > 0

        return await self._transaction(operation)

    async def remove_account(self, username: str) -> int:
        normalized = _username(username)

        def operation(conn: sqlite3.Connection) -> int:
            deleted = conn.execute(
                "DELETE FROM subscriptions WHERE username = ?", (normalized,)
            ).rowcount
            self._purge_account_state(conn, normalized)
            return max(0, deleted)

        return await self._transaction(operation)

    @staticmethod
    def _purge_account_state(conn: sqlite3.Connection, username: str) -> None:
        conn.execute("DELETE FROM outbox WHERE username = ?", (username,))
        conn.execute("DELETE FROM fetch_state WHERE username = ?", (username,))
        conn.execute("DELETE FROM account_state WHERE username = ?", (username,))

    async def add_list_subscription(
        self,
        *,
        scope_key: str,
        platform: str,
        group_id: int,
        target_data: str,
        list_id: int,
        name: str,
        cursor: int | None = None,
    ) -> bool:
        source = list_source_key(list_id)

        def operation(conn: sqlite3.Connection) -> bool:
            result = conn.execute(
                """
                INSERT OR IGNORE INTO list_subscriptions(
                    scope_key, platform, group_id, target_data, list_id, name, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    scope_key,
                    platform,
                    group_id,
                    target_data,
                    int(list_id),
                    name,
                    time.time(),
                ),
            )
            conn.execute(
                "INSERT INTO account_state(username) VALUES (?) ON CONFLICT(username) DO NOTHING",
                (source,),
            )
            if cursor is not None:
                self._upsert_cursor(conn, source, cursor)
            return result.rowcount > 0

        return await self._transaction(operation)

    async def remove_list_subscription(self, scope_key: str, list_id: int) -> bool:
        source = list_source_key(list_id)

        def operation(conn: sqlite3.Connection) -> bool:
            deleted = conn.execute(
                "DELETE FROM list_subscriptions WHERE scope_key = ? AND list_id = ?",
                (scope_key, int(list_id)),
            ).rowcount
            if deleted:
                remaining = conn.execute(
                    "SELECT 1 FROM list_subscriptions WHERE list_id = ? LIMIT 1",
                    (int(list_id),),
                ).fetchone()
                if remaining is None:
                    self._purge_account_state(conn, source)
            return deleted > 0

        return await self._transaction(operation)

    async def remove_list_account(self, list_id: int) -> int:
        source = list_source_key(list_id)

        def operation(conn: sqlite3.Connection) -> int:
            deleted = conn.execute(
                "DELETE FROM list_subscriptions WHERE list_id = ?", (int(list_id),)
            ).rowcount
            self._purge_account_state(conn, source)
            return max(0, deleted)

        return await self._transaction(operation)

    async def list_subscriptions_for_scope(
        self, scope_key: str
    ) -> list[ListSubscription]:
        return await self._list_subscriptions("WHERE scope_key = ?", (scope_key,))

    async def list_subscriptions_for_list(self, list_id: int) -> list[ListSubscription]:
        return await self._list_subscriptions("WHERE list_id = ?", (int(list_id),))

    async def list_source_keys(self) -> list[str]:
        return await self._read(
            lambda conn: [
                list_source_key(int(row[0]))
                for row in conn.execute(
                    "SELECT DISTINCT list_id FROM list_subscriptions ORDER BY list_id"
                ).fetchall()
            ]
        )

    async def _list_subscriptions(
        self, clause: str, params: tuple[Any, ...]
    ) -> list[ListSubscription]:
        def operation(conn: sqlite3.Connection) -> list[ListSubscription]:
            rows = conn.execute(
                f"SELECT * FROM list_subscriptions {clause} ORDER BY list_id", params
            ).fetchall()
            return [
                ListSubscription(
                    scope_key=str(row["scope_key"]),
                    platform=str(row["platform"]),
                    group_id=int(row["group_id"]),
                    target_data=str(row["target_data"]),
                    list_id=int(row["list_id"]),
                    name=str(row["name"]),
                )
                for row in rows
            ]

        return await self._read(operation)

    async def subscriptions_for_scope(self, scope_key: str) -> list[Subscription]:
        return await self._subscriptions("WHERE scope_key = ?", (scope_key,))

    async def subscriptions_for_username(self, username: str) -> list[Subscription]:
        return await self._subscriptions("WHERE username = ?", (_username(username),))

    async def usernames(self) -> list[str]:
        return await self._read(
            lambda conn: [
                str(row[0])
                for row in conn.execute(
                    "SELECT DISTINCT username FROM subscriptions ORDER BY username"
                ).fetchall()
            ]
        )

    async def get_account_state(self, username: str) -> AccountState:
        normalized = _username(username)

        def operation(conn: sqlite3.Connection) -> AccountState:
            conn.execute(
                "INSERT INTO account_state(username) VALUES (?) ON CONFLICT(username) DO NOTHING",
                (normalized,),
            )
            row = conn.execute(
                "SELECT * FROM account_state WHERE username = ?", (normalized,)
            ).fetchone()
            return AccountState(
                username=normalized,
                user_id=int(row["user_id"]) if row["user_id"] is not None else None,
                failures=int(row["failures"]),
                retry_at=float(row["retry_at"]),
                last_posted_at=float(row["last_posted_at"]),
            )

        return await self._transaction(operation)

    async def set_user_id(self, username: str, user_id: int) -> None:
        await self._execute(
            "UPDATE account_state SET user_id = ? WHERE username = ?",
            (int(user_id), _username(username)),
        )

    async def complete_poll(
        self, username: str, *, last_posted_at: float | None = None
    ) -> None:
        await self._execute(
            """
            UPDATE account_state
            SET failures = 0, retry_at = 0, last_error = NULL,
                last_posted_at = MAX(last_posted_at, COALESCE(?, last_posted_at))
            WHERE username = ?
            """,
            (last_posted_at, _username(username)),
        )

    async def defer_poll(self, username: str, retry_at: float, error: str) -> None:
        await self._execute(
            """
            UPDATE account_state
            SET failures = failures + 1, retry_at = ?, last_error = ?
            WHERE username = ?
            """,
            (retry_at, error[:1000], _username(username)),
        )

    async def get_cursor(self, username: str) -> int | None:
        return await self._read(
            lambda conn: _first_int(
                conn.execute(
                    "SELECT last_seen_id FROM fetch_state WHERE username = ?",
                    (_username(username),),
                ).fetchone()
            )
        )

    async def set_cursor(self, username: str, tweet_id: int) -> None:
        await self._transaction(
            lambda conn: self._upsert_cursor(conn, _username(username), tweet_id)
        )

    async def enqueue_posts(self, username: str, posts: list[XPost]) -> int:
        normalized = _username(username)
        if not posts:
            return 0

        def operation(conn: sqlite3.Connection) -> int:
            subscriptions = conn.execute(
                "SELECT * FROM subscriptions WHERE username = ?", (normalized,)
            ).fetchall()
            inserted = 0
            now = time.time()
            for post in posts:
                payload = json.dumps(post.to_dict(), ensure_ascii=False)
                for subscription in subscriptions:
                    result = conn.execute(
                        """
                        INSERT OR IGNORE INTO outbox(
                            scope_key, platform, group_id, target_data, username,
                            tweet_id, payload, status, attempts, next_attempt_at, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', 0, ?, ?)
                        """,
                        (
                            subscription["scope_key"],
                            subscription["platform"],
                            subscription["group_id"],
                            subscription["target_data"],
                            normalized,
                            post.id,
                            payload,
                            now,
                            now,
                        ),
                    )
                    inserted += max(0, result.rowcount)
            self._upsert_cursor(conn, normalized, max(int(post.id) for post in posts))
            return inserted

        return await self._transaction(operation)

    async def enqueue_list_posts(self, list_id: int, posts: list[XPost]) -> int:
        source = list_source_key(list_id)
        if not posts:
            return 0

        def operation(conn: sqlite3.Connection) -> int:
            subscriptions = conn.execute(
                "SELECT * FROM list_subscriptions WHERE list_id = ?", (int(list_id),)
            ).fetchall()
            inserted = 0
            now = time.time()
            for post in posts:
                payload = json.dumps(post.to_dict(), ensure_ascii=False)
                for subscription in subscriptions:
                    # UNIQUE(scope_key, tweet_id) makes this a precise no-op when
                    # the same tweet already reached the group via another source.
                    result = conn.execute(
                        """
                        INSERT OR IGNORE INTO outbox(
                            scope_key, platform, group_id, target_data, username,
                            tweet_id, payload, status, attempts, next_attempt_at, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', 0, ?, ?)
                        """,
                        (
                            subscription["scope_key"],
                            subscription["platform"],
                            subscription["group_id"],
                            subscription["target_data"],
                            source,
                            post.id,
                            payload,
                            now,
                            now,
                        ),
                    )
                    inserted += max(0, result.rowcount)
            self._upsert_cursor(conn, source, max(int(post.id) for post in posts))
            return inserted

        return await self._transaction(operation)

    async def due_outbox(self, limit: int = 10) -> list[OutboxItem]:
        now = time.time()

        def operation(conn: sqlite3.Connection) -> list[OutboxItem]:
            rows = conn.execute(
                """
                SELECT * FROM outbox
                WHERE status = 'pending' AND next_attempt_at <= ?
                ORDER BY CAST(tweet_id AS INTEGER), id
                LIMIT ?
                """,
                (now, max(1, limit)),
            ).fetchall()
            return [
                OutboxItem(
                    id=int(row["id"]),
                    scope_key=str(row["scope_key"]),
                    platform=str(row["platform"]),
                    group_id=int(row["group_id"]),
                    target_data=str(row["target_data"]),
                    post=XPost.from_dict(json.loads(row["payload"])),
                    attempts=int(row["attempts"]),
                )
                for row in rows
            ]

        return await self._read(operation)

    async def mark_sent(self, outbox_id: int) -> None:
        await self._execute(
            "UPDATE outbox SET status = 'sent', sent_at = ?, last_error = NULL WHERE id = ?",
            (time.time(), outbox_id),
        )

    async def mark_failed(self, outbox_id: int, retry_at: float, error: str) -> None:
        await self._execute(
            """
            UPDATE outbox SET attempts = attempts + 1, next_attempt_at = ?, last_error = ?
            WHERE id = ?
            """,
            (retry_at, error[:1000], outbox_id),
        )

    async def mark_dead(self, outbox_id: int, error: str) -> None:
        """Permanently give up on an outbox item so it is never dispatched again."""
        await self._execute(
            "UPDATE outbox SET status = 'failed', last_error = ? WHERE id = ?",
            (error[:1000], outbox_id),
        )

    async def acquire_rate_permit(
        self, endpoint: str, minimum_interval: float
    ) -> RatePermit:
        now = time.time()

        def operation(conn: sqlite3.Connection) -> RatePermit:
            row = conn.execute(
                "SELECT next_allowed_at, cooldown_until FROM endpoint_rate WHERE endpoint = ?",
                (endpoint,),
            ).fetchone()
            retry_at = max(float(row[0]), float(row[1])) if row else 0.0
            if retry_at > now:
                return RatePermit(False, retry_at)
            conn.execute(
                """
                INSERT INTO endpoint_rate(endpoint, next_allowed_at, cooldown_until)
                VALUES (?, ?, 0)
                ON CONFLICT(endpoint) DO UPDATE SET next_allowed_at = excluded.next_allowed_at
                """,
                (endpoint, now + max(0.0, minimum_interval)),
            )
            return RatePermit(True, now)

        return await self._transaction(operation)

    async def set_rate_cooldown(self, endpoint: str, retry_at: float) -> None:
        await self._execute(
            """
            INSERT INTO endpoint_rate(endpoint, next_allowed_at, cooldown_until)
            VALUES (?, 0, ?)
            ON CONFLICT(endpoint) DO UPDATE SET
                cooldown_until = MAX(cooldown_until, excluded.cooldown_until)
            """,
            (endpoint, retry_at),
        )

    async def claim_reaction(
        self, platform: str, group_id: int, message_id: int, actor_id: int
    ) -> bool:
        now = time.time()

        def operation(conn: sqlite3.Connection) -> bool:
            conn.execute(
                "DELETE FROM reaction_forwards WHERE created_at < ?",
                (now - 90 * 86400,),
            )
            result = conn.execute(
                """
                INSERT OR IGNORE INTO reaction_forwards(
                    platform, group_id, message_id, actor_id, created_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (platform, group_id, message_id, actor_id, now),
            )
            return result.rowcount > 0

        return await self._transaction(operation)

    async def _subscriptions(
        self, clause: str, params: tuple[Any, ...]
    ) -> list[Subscription]:
        def operation(conn: sqlite3.Connection) -> list[Subscription]:
            rows = conn.execute(
                f"SELECT * FROM subscriptions {clause} ORDER BY username", params
            ).fetchall()
            return [
                Subscription(
                    scope_key=str(row["scope_key"]),
                    platform=str(row["platform"]),
                    group_id=int(row["group_id"]),
                    target_data=str(row["target_data"]),
                    username=str(row["username"]),
                    name=str(row["name"]),
                )
                for row in rows
            ]

        return await self._read(operation)

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
                CREATE TABLE IF NOT EXISTS subscriptions (
                    scope_key TEXT NOT NULL,
                    platform TEXT NOT NULL,
                    group_id INTEGER NOT NULL,
                    target_data TEXT NOT NULL,
                    username TEXT NOT NULL COLLATE NOCASE,
                    name TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    PRIMARY KEY(scope_key, username)
                );
                CREATE TABLE IF NOT EXISTS account_state (
                    username TEXT PRIMARY KEY COLLATE NOCASE,
                    user_id INTEGER,
                    failures INTEGER NOT NULL DEFAULT 0,
                    retry_at REAL NOT NULL DEFAULT 0,
                    last_error TEXT,
                    last_posted_at REAL NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS fetch_state (
                    username TEXT PRIMARY KEY COLLATE NOCASE,
                    last_seen_id INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS outbox (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    scope_key TEXT NOT NULL,
                    platform TEXT NOT NULL,
                    group_id INTEGER NOT NULL,
                    target_data TEXT NOT NULL,
                    username TEXT NOT NULL COLLATE NOCASE,
                    tweet_id TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    status TEXT NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    next_attempt_at REAL NOT NULL,
                    last_error TEXT,
                    created_at REAL NOT NULL,
                    sent_at REAL,
                    UNIQUE(scope_key, username, tweet_id)
                );
                CREATE INDEX IF NOT EXISTS outbox_due_idx
                    ON outbox(status, next_attempt_at, id);
                CREATE TABLE IF NOT EXISTS endpoint_rate (
                    endpoint TEXT PRIMARY KEY,
                    next_allowed_at REAL NOT NULL DEFAULT 0,
                    cooldown_until REAL NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS reaction_forwards (
                    platform TEXT NOT NULL,
                    group_id INTEGER NOT NULL,
                    message_id INTEGER NOT NULL,
                    actor_id INTEGER NOT NULL,
                    created_at REAL NOT NULL,
                    PRIMARY KEY(platform, group_id, message_id, actor_id)
                );
                CREATE TABLE IF NOT EXISTS list_subscriptions (
                    scope_key TEXT NOT NULL,
                    platform TEXT NOT NULL,
                    group_id INTEGER NOT NULL,
                    target_data TEXT NOT NULL,
                    list_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    PRIMARY KEY(scope_key, list_id)
                );
                """
            )
            self._ensure_outbox_scope_tweet_index(conn)

    @staticmethod
    def _ensure_outbox_scope_tweet_index(conn: sqlite3.Connection) -> None:
        # Precise dispatch: a group receives a given tweet at most once, no
        # matter how many subscriptions (user and/or list) matched it.
        exists = conn.execute(
            "SELECT 1 FROM sqlite_master "
            "WHERE type = 'index' AND name = 'outbox_scope_tweet_idx'"
        ).fetchone()
        if exists is not None:
            return
        # One-time migration: collapse any pre-existing rows sharing
        # (scope_key, tweet_id) so the unique index can be created.
        conn.execute(
            "DELETE FROM outbox WHERE id NOT IN "
            "(SELECT MIN(id) FROM outbox GROUP BY scope_key, tweet_id)"
        )
        conn.execute(
            "CREATE UNIQUE INDEX outbox_scope_tweet_idx ON outbox(scope_key, tweet_id)"
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

    @staticmethod
    def _upsert_cursor(conn: sqlite3.Connection, username: str, tweet_id: int) -> None:
        conn.execute(
            """
            INSERT INTO fetch_state(username, last_seen_id) VALUES (?, ?)
            ON CONFLICT(username) DO UPDATE SET
                last_seen_id = MAX(last_seen_id, excluded.last_seen_id)
            """,
            (username, int(tweet_id)),
        )


def _username(value: str) -> str:
    return str(value).strip().lstrip("@").lower()


def _first_int(row: sqlite3.Row | None) -> int | None:
    return int(row[0]) if row is not None else None


__all__ = [
    "AccountState",
    "LIST_SOURCE_PREFIX",
    "ListSubscription",
    "OutboxItem",
    "RatePermit",
    "Subscription",
    "XStore",
    "list_source_key",
    "parse_list_source_key",
]
