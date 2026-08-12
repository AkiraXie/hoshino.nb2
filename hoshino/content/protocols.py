"""Shared protocols for the two-phase ingest/dispatch pipeline.

OutboxStore — durable delivery queue (persist → notify).
ArchiveStore — long-term post archive (files + metadata).
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from .engine import Post, PostMessage


@runtime_checkable
class OutboxItem(Protocol):
    """A single pending delivery item read from the outbox."""

    @property
    def id(self) -> int: ...

    @property
    def post(self) -> Post: ...

    @property
    def attempts(self) -> int: ...


@runtime_checkable
class OutboxStore(Protocol):
    """Durable delivery queue: enqueue after persist, dispatch once."""

    async def enqueue_posts(self, uid: str, posts: list[Post]) -> int:
        """Fan-out posts to all subscriptions; return number of rows inserted."""
        ...

    async def due_outbox(self, limit: int = 10) -> list[Any]:
        """Return up to *limit* items whose next_attempt_at <= now."""
        ...

    async def mark_sent(self, item_id: int) -> None: ...

    async def mark_failed(self, item_id: int, retry_at: float, error: str) -> None: ...

    async def mark_dead(self, item_id: int, error: str) -> None:
        """Permanently give up on an item so it is never dispatched again."""
        ...


@runtime_checkable
class ArchiveStore(Protocol):
    """Long-term post archive: save media + metadata, load on demand."""

    async def save(self, post: Post, message: PostMessage) -> PostMessage:
        """Persist *message* assets under the archive tree.

        Returns a new PostMessage whose resource paths point into the
        archive (so the caller can safely discard temporary files).
        """
        ...

    async def load(self, uid: str, post_id: str) -> PostMessage | None:
        """Load a previously archived PostMessage, or None if missing."""
        ...


__all__ = [
    "ArchiveStore",
    "OutboxItem",
    "OutboxStore",
]
