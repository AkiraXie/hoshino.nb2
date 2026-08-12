"""Weibo dispatch behavior: oversized video skipping and no send retries."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_weibo_oversized_video_dropped_from_message_but_kept_on_disk(
    tmp_path: Path,
):
    from hoshino.content import PostMessage
    from hoshino.modules.information.weibo.internal.post_runtime import (
        MAX_VIDEO_UPLOAD_BYTES,
        filter_oversized_videos,
    )

    cover = tmp_path / "cover.jpg"
    cover.write_bytes(b"cover")
    big_video = tmp_path / "big.mp4"
    big_video.write_bytes(b"x" * (MAX_VIDEO_UPLOAD_BYTES + 1))
    small_video = tmp_path / "small.mp4"
    small_video.write_bytes(b"tiny")

    message = PostMessage(text="t", images=[cover], videos=[big_video, small_video])
    filtered = filter_oversized_videos(message)

    assert filtered.images == [cover]
    assert filtered.videos == [small_video]
    # The oversized file is only kept locally; it must not be deleted.
    assert big_video.exists()


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_weibo_dispatch_failure_dead_letters_without_retry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    from hoshino.modules.information.weibo.internal import sub_runtime
    from hoshino.modules.information.weibo.internal.outbox import WeiboOutboxStore
    from hoshino.modules.information.weibo.post import WeiboPost

    store = WeiboOutboxStore(tmp_path / "outbox.db")
    await store.enqueue(
        group_id=123,
        target_data="{}",
        uid="user1",
        post_id="p001",
        post_payload={"uid": "user1", "id": "p001", "content": "hello"},
        message_payload={"text": "hello", "content": "hello"},
    )

    async def fake_enable_groups():
        return {123: [object()]}

    monkeypatch.setattr(sub_runtime.sv, "get_enable_groups", fake_enable_groups)
    monkeypatch.setattr(
        sub_runtime,
        "get_group_config",
        lambda group_id: SimpleNamespace(
            only_pic=0,
            send_screenshot=0,
            send_segments=0,
        ),
    )

    async def boom(self, *args, **kwargs):
        raise RuntimeError("send failed")

    monkeypatch.setattr(WeiboPost, "send", boom)

    dispatched = await sub_runtime.DispatchMainline(store).dispatch_due()

    assert dispatched == 0
    conn = sqlite3.connect(tmp_path / "outbox.db")
    row = conn.execute(
        "SELECT status, attempts FROM weibo_outbox WHERE id = 1"
    ).fetchone()
    conn.close()
    assert row == ("dead", 0)
    assert await store.due_outbox() == []
