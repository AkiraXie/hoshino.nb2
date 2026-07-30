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


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_persist_dedupes_media_shared_with_repost(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """A retweet re-carries the source media; the same URL must be kept once."""
    media_module = _x_module("media")
    post_module = _x_module("post")

    media_store = media_module.XMediaStore()
    monkeypatch.setattr(media_store, "root", tmp_path)
    downloads: list[tuple[str, str]] = []

    async def fake_download(post, url, is_video):
        downloads.append((post.id, url))
        return tmp_path / post.uid / post.id / Path(url).name

    monkeypatch.setattr(media_store, "_download", fake_download)
    try:
        repost = post_module.XPost(
            uid="bob",
            id="100",
            content="original",
            images=[
                "https://pbs.twimg.com/a.jpg",
                "https://pbs.twimg.com/b.jpg",
            ],
        )
        post = post_module.XPost(
            uid="alice",
            id="201",
            content="retweet",
            images=["https://pbs.twimg.com/a.jpg"],
            repost=repost,
        )
        result = await media_store.persist(post, max_media=10)
    finally:
        await media_store.close()

    downloaded_urls = [url for _, url in downloads]
    assert downloaded_urls.count("https://pbs.twimg.com/a.jpg") == 1
    assert sorted(downloaded_urls) == [
        "https://pbs.twimg.com/a.jpg",
        "https://pbs.twimg.com/b.jpg",
    ]
    assert len(result.images) == 2
    assert {Path(path).name for path in result.images} == {"a.jpg", "b.jpg"}


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_persist_saves_original_media_once_across_retweets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """No matter how many retweets, the original media is downloaded once."""
    media_module = _x_module("media")
    post_module = _x_module("post")

    media_store = media_module.XMediaStore()
    monkeypatch.setattr(media_store, "root", tmp_path)
    stream_calls: list[str] = []

    class FakeResponse:
        def __init__(self, data: bytes) -> None:
            self.headers = {"content-length": str(len(data))}
            self._data = data

        def raise_for_status(self) -> None:
            pass

        async def aiter_bytes(self):
            yield self._data

    class FakeStream:
        def __init__(self, data: bytes) -> None:
            self._data = data

        async def __aenter__(self):
            return FakeResponse(self._data)

        async def __aexit__(self, *args):
            return None

    def fake_stream(method, url, **kwargs):
        stream_calls.append(url)
        return FakeStream(b"img-bytes")

    monkeypatch.setattr(media_store.client, "stream", fake_stream)

    def retweet(tweet_id: str) -> "post_module.XPost":
        original = post_module.XPost(
            uid="bob",
            id="100",
            content="original",
            images=["https://pbs.twimg.com/a.jpg"],
        )
        return post_module.XPost(
            uid="alice",
            id=tweet_id,
            content="retweet",
            images=["https://pbs.twimg.com/a.jpg"],
            repost=original,
        )

    try:
        first = await media_store.persist(retweet("201"), max_media=10)
        second = await media_store.persist(retweet("202"), max_media=10)
    finally:
        await media_store.close()

    saved = tmp_path / "bob" / "100" / "a.jpg"
    assert stream_calls == ["https://pbs.twimg.com/a.jpg"]
    assert saved.exists()
    assert first.images == [str(saved)]
    assert second.images == [str(saved)]
