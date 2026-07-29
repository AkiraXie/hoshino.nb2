"""Weibo outbox durability tests: enqueue, dedup, retry, restart recovery."""

from __future__ import annotations

import time
from pathlib import Path

import pytest


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_weibo_outbox_enqueue_and_due(tmp_path: Path):
    from hoshino.modules.information.weibo.internal.outbox import WeiboOutboxStore

    store = WeiboOutboxStore(tmp_path / "outbox.db")
    inserted = await store.enqueue(
        group_id=123,
        target_data='{"id":"123"}',
        uid="user1",
        post_id="p001",
        post_payload={"uid": "user1", "id": "p001", "content": "hello"},
        message_payload={"text": "hello", "content": "hello"},
    )
    assert inserted is True

    due = await store.due_outbox()
    assert len(due) == 1
    item = due[0]
    assert item.group_id == 123
    assert item.uid == "user1"
    assert item.post_id == "p001"
    assert item.post_payload["content"] == "hello"
    assert item.attempts == 0


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_weibo_outbox_deduplication(tmp_path: Path):
    from hoshino.modules.information.weibo.internal.outbox import WeiboOutboxStore

    store = WeiboOutboxStore(tmp_path / "outbox.db")
    kwargs = {
        "group_id": 123,
        "target_data": "{}",
        "uid": "user1",
        "post_id": "p001",
        "post_payload": {"uid": "user1", "id": "p001"},
        "message_payload": {"text": "hi"},
    }
    assert await store.enqueue(**kwargs) is True
    assert await store.enqueue(**kwargs) is False

    # Same post to a different group is allowed
    assert await store.enqueue(**{**kwargs, "group_id": 456}) is True
    assert await store.pending_count() == 2


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_weibo_outbox_mark_sent(tmp_path: Path):
    from hoshino.modules.information.weibo.internal.outbox import WeiboOutboxStore

    store = WeiboOutboxStore(tmp_path / "outbox.db")
    await store.enqueue(
        group_id=1,
        target_data="{}",
        uid="u",
        post_id="p1",
        post_payload={},
        message_payload={},
    )
    due = await store.due_outbox()
    await store.mark_sent(due[0].id)

    assert await store.due_outbox() == []
    assert await store.pending_count() == 0


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_weibo_outbox_retry_backoff(tmp_path: Path):
    from hoshino.modules.information.weibo.internal.outbox import WeiboOutboxStore

    store = WeiboOutboxStore(tmp_path / "outbox.db")
    await store.enqueue(
        group_id=1,
        target_data="{}",
        uid="u",
        post_id="p1",
        post_payload={},
        message_payload={},
    )
    due = await store.due_outbox()
    item = due[0]

    # Mark failed with a future retry time
    future = time.time() + 9999
    await store.mark_failed(item.id, future, "timeout")

    # Item should NOT be due yet
    assert await store.due_outbox() == []

    # Mark failed with a past retry time — item becomes due again
    await store.mark_failed(item.id, time.time() - 1, "timeout again")
    retried = await store.due_outbox()
    assert len(retried) == 1
    assert retried[0].attempts == 2


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_weibo_outbox_mark_dead(tmp_path: Path):
    from hoshino.modules.information.weibo.internal.outbox import WeiboOutboxStore

    store = WeiboOutboxStore(tmp_path / "outbox.db")
    await store.enqueue(
        group_id=1,
        target_data="{}",
        uid="u",
        post_id="p1",
        post_payload={},
        message_payload={},
    )
    due = await store.due_outbox()
    await store.mark_dead(due[0].id, "exceeded max attempts")

    assert await store.due_outbox() == []
    assert await store.pending_count() == 0


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_weibo_outbox_restart_recovery(tmp_path: Path):
    """Pending items survive a store restart (new instance, same DB path)."""
    from hoshino.modules.information.weibo.internal.outbox import WeiboOutboxStore

    db_path = tmp_path / "outbox.db"
    store = WeiboOutboxStore(db_path)
    await store.enqueue(
        group_id=10,
        target_data='{"id":"10"}',
        uid="blogger",
        post_id="w123",
        post_payload={"uid": "blogger", "id": "w123", "content": "persisted"},
        message_payload={"text": "persisted"},
    )

    # Simulate restart: new instance on the same file
    restarted = WeiboOutboxStore(db_path)
    due = await restarted.due_outbox()
    assert len(due) == 1
    assert due[0].post_payload["content"] == "persisted"
    assert due[0].group_id == 10


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_weibo_outbox_cleanup_old(tmp_path: Path):
    from hoshino.modules.information.weibo.internal.outbox import WeiboOutboxStore

    store = WeiboOutboxStore(tmp_path / "outbox.db")
    await store.enqueue(
        group_id=1,
        target_data="{}",
        uid="u",
        post_id="p1",
        post_payload={},
        message_payload={},
    )
    due = await store.due_outbox()
    await store.mark_sent(due[0].id)

    # Nothing old enough to clean
    assert await store.cleanup_old(days=7) == 0

    # Manually backdate created_at to trigger cleanup
    import sqlite3

    conn = sqlite3.connect(tmp_path / "outbox.db")
    conn.execute(
        "UPDATE weibo_outbox SET created_at = ? WHERE id = ?",
        (time.time() - 8 * 86400, due[0].id),
    )
    conn.commit()
    conn.close()

    assert await store.cleanup_old(days=7) == 1


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_weibo_outbox_serialization_roundtrip():
    from hoshino.content import PostMessage
    from hoshino.modules.information.weibo.internal.outbox import (
        deserialize_post_message,
        serialize_post_message,
    )

    original = PostMessage(
        text="test post",
        content="test post",
        screenshot=Path("/data/img/shot.png"),
        images=[Path("/data/img/1.jpg"), Path("/data/img/2.jpg")],
        videos=[Path("/data/video/v.mp4")],
    )
    data = serialize_post_message(original)
    restored = deserialize_post_message(data)

    assert restored.text == original.text
    assert restored.content == original.content
    assert restored.screenshot == original.screenshot
    assert restored.images == original.images
    assert restored.videos == original.videos


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_weibo_outbox_claim_prevents_double_dispatch(tmp_path: Path):
    """Overlapping dispatch runs must not read the same item twice.

    The dispatch job can run with concurrent instances (APScheduler
    max_instances=2); without claiming, a slow batch let a second run re-read
    still-pending rows and send the same article twice.
    """
    from hoshino.modules.information.weibo.internal.outbox import WeiboOutboxStore

    store = WeiboOutboxStore(tmp_path / "outbox.db")
    await store.enqueue(
        group_id=1,
        target_data="{}",
        uid="u",
        post_id="p1",
        post_payload={},
        message_payload={},
    )

    first = await store.due_outbox()
    second = await store.due_outbox()
    assert [item.id for item in first] == [1]
    assert second == []

    # Finalizing the item keeps it from being dispatched again.
    await store.mark_sent(first[0].id)
    assert await store.due_outbox() == []


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_weibo_outbox_claim_expires_for_crash_recovery(tmp_path: Path):
    """If delivery crashes before finalizing, the lease expires and retries."""
    import sqlite3

    from hoshino.modules.information.weibo.internal.outbox import WeiboOutboxStore

    store = WeiboOutboxStore(tmp_path / "outbox.db")
    await store.enqueue(
        group_id=1,
        target_data="{}",
        uid="u",
        post_id="p1",
        post_payload={},
        message_payload={},
    )

    assert len(await store.due_outbox()) == 1
    assert await store.due_outbox() == []  # claimed, not due

    # Simulate the lease expiring after a crash mid-delivery.
    conn = sqlite3.connect(tmp_path / "outbox.db")
    conn.execute("UPDATE weibo_outbox SET next_attempt_at = ?", (time.time() - 1,))
    conn.commit()
    conn.close()

    recovered = await store.due_outbox()
    assert [item.id for item in recovered] == [1]
