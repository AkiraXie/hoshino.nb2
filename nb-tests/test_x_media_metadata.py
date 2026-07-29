"""X media metadata (message.json) archive tests."""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest


def _x_module(name: str):
    return importlib.import_module(f"hoshino.modules.info-x.x.{name}")


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_write_metadata_creates_message_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    media_module = _x_module("media")
    post_module = _x_module("post")

    media_store = media_module.XMediaStore()
    monkeypatch.setattr(media_store, "root", tmp_path)
    try:
        post = post_module.XPost(
            uid="alice",
            id="201",
            content="hello world",
            nickname="Alice",
            timestamp=1700000000.0,
            url="https://fxtwitter.com/alice/status/201",
            likes=42,
            images=[str(tmp_path / "alice" / "201" / "img1.jpg")],
            videos=[],
        )
        await media_store.write_metadata(post)

        metadata_path = tmp_path / "alice" / "201" / "message.json"
        assert metadata_path.exists()
        data = json.loads(metadata_path.read_text(encoding="utf-8"))
        assert data["uid"] == "alice"
        assert data["id"] == "201"
        assert data["content"] == "hello world"
        assert data["nickname"] == "Alice"
        assert data["timestamp"] == 1700000000.0
        assert data["likes"] == 42
        assert data["images"] == ["img1.jpg"]
        assert data["videos"] == []
        assert data["repost"] is None
    finally:
        await media_store.close()


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_write_metadata_includes_repost(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    media_module = _x_module("media")
    post_module = _x_module("post")

    media_store = media_module.XMediaStore()
    monkeypatch.setattr(media_store, "root", tmp_path)
    try:
        repost = post_module.XPost(
            uid="bob",
            id="100",
            content="original post",
            nickname="Bob",
            url="https://fxtwitter.com/bob/status/100",
        )
        post = post_module.XPost(
            uid="alice",
            id="202",
            content="RT comment",
            nickname="Alice",
            timestamp=1700000001.0,
            url="https://fxtwitter.com/alice/status/202",
            repost=repost,
        )
        await media_store.write_metadata(post)

        data = json.loads(
            (tmp_path / "alice" / "202" / "message.json").read_text(encoding="utf-8")
        )
        assert data["repost"] is not None
        assert data["repost"]["uid"] == "bob"
        assert data["repost"]["id"] == "100"
        assert data["repost"]["content"] == "original post"
    finally:
        await media_store.close()


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_write_metadata_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    media_module = _x_module("media")
    post_module = _x_module("post")

    media_store = media_module.XMediaStore()
    monkeypatch.setattr(media_store, "root", tmp_path)
    try:
        post = post_module.XPost(
            uid="alice", id="301", content="first", nickname="Alice"
        )
        await media_store.write_metadata(post)

        # Modify content and write again — should NOT overwrite
        post.content = "modified"
        await media_store.write_metadata(post)

        data = json.loads(
            (tmp_path / "alice" / "301" / "message.json").read_text(encoding="utf-8")
        )
        assert data["content"] == "first"
    finally:
        await media_store.close()


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_write_metadata_filters_http_urls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """HTTP URLs (not yet downloaded) are excluded from metadata filenames."""
    media_module = _x_module("media")
    post_module = _x_module("post")

    media_store = media_module.XMediaStore()
    monkeypatch.setattr(media_store, "root", tmp_path)
    try:
        post = post_module.XPost(
            uid="alice",
            id="401",
            content="mixed",
            nickname="Alice",
            images=[
                str(tmp_path / "alice" / "401" / "local.jpg"),
                "https://pbs.twimg.com/remote.jpg",
            ],
            videos=["https://video.twimg.com/remote.mp4"],
        )
        await media_store.write_metadata(post)

        data = json.loads(
            (tmp_path / "alice" / "401" / "message.json").read_text(encoding="utf-8")
        )
        assert data["images"] == ["local.jpg"]
        assert data["videos"] == []
    finally:
        await media_store.close()
