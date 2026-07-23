"""X workflow, Telegram API, and platform routing coverage."""

from __future__ import annotations

import importlib
import json
import time
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import pytest
from nonebot import get_driver
from nonebot.adapters.telegram import Adapter as TelegramAdapter
from nonebot.adapters.telegram import Bot as TelegramBot
from nonebot.adapters.telegram.config import BotConfig as TelegramBotConfig
from nonebot.adapters.telegram.model import InputMediaPhoto
from nonebot.drivers import Response
from nonebot_plugin_alconna.uniseg import UniMessage
from twscrape.models import (
    Media,
    Tweet,
    User,
)


def _x_module(name: str):
    return importlib.import_module(f"hoshino.modules.info-x.x.{name}")


def _telegram_bot() -> TelegramBot:
    adapter = TelegramAdapter(get_driver())
    return TelegramBot(
        adapter,
        self_id="10000",
        config=TelegramBotConfig(
            token="10000:test",
            api_server="https://fake.invalid/",
        ),
    )


def _telegram_message(message_id: int = 7) -> dict[str, Any]:
    return {
        "message_id": message_id,
        "date": 1,
        "chat": {"id": -100123456, "type": "supergroup", "title": "test"},
        "from": {"id": 10000, "is_bot": True, "first_name": "Bot"},
        "text": "ok",
    }


def _tweet(tweet_id: int, *, content: str = "", username: str = "alice") -> Tweet:
    user = User(
        id=1,
        id_str="1",
        url=f"https://x.com/{username}",
        username=username,
        displayname=username.title(),
        rawDescription="",
        created=datetime(2020, 1, 1, tzinfo=timezone.utc),
        followersCount=0,
        friendsCount=0,
        statusesCount=0,
        favouritesCount=0,
        listedCount=0,
        mediaCount=0,
        location="",
        profileImageUrl="",
    )
    return Tweet(
        id=tweet_id,
        id_str=str(tweet_id),
        url=f"https://x.com/{username}/status/{tweet_id}",
        date=datetime.now(timezone.utc),
        user=user,
        lang="en",
        rawContent=content,
        replyCount=0,
        retweetCount=0,
        likeCount=0,
        quoteCount=0,
        bookmarkedCount=0,
        conversationId=tweet_id,
        conversationIdStr=str(tweet_id),
        hashtags=[],
        cashtags=[],
        mentionedUsers=[],
        links=[],
        media=Media(),
    )


class RecordingLogger:
    def __init__(self) -> None:
        self.warnings: list[str] = []
        self.errors: list[str] = []

    def info(self, message: str) -> None:
        pass

    def warning(self, message: str) -> None:
        self.warnings.append(message)

    def error(self, message: str, exception: object = False) -> None:
        self.errors.append(message)


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_x_post_media_reaches_fake_telegram_api(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    from hoshino.platform import group_target, send_to_target

    post_module = _x_module("post")
    image_path = tmp_path / "image.jpg"
    video_path = tmp_path / "video.mp4"
    image_path.write_bytes(b"image")
    video_path.write_bytes(b"video")
    post = post_module.XPost(
        uid="alice",
        id="101",
        content="media",
        timestamp=1,
        images=[str(image_path)],
        videos=[str(video_path)],
    )
    bot = _telegram_bot()
    endpoints: list[str] = []

    async def fake_request(request):
        endpoint = str(request.url).rsplit("/", 1)[-1]
        endpoints.append(endpoint)
        return Response(
            200,
            content=json.dumps(
                {
                    "ok": True,
                    "result": [_telegram_message(9), _telegram_message(10)],
                }
            ).encode(),
        )

    monkeypatch.setattr(bot.adapter, "request", fake_request)
    message = post.render_message(await post.get_message())[0]

    await send_to_target(bot, group_target(-100123456), message)

    assert endpoints == ["sendMediaGroup"]


@pytest.mark.usefixtures("_nonebot_bootstrap")
def test_telegram_raw_reaction_parser_and_allowed_updates():
    from nonebot.adapters.telegram import Event

    from hoshino.platform import get_reaction_info
    from hoshino.platform.telegram.bootstrap import apply_patches
    from hoshino.platform.telegram.events import MessageReactionEvent

    apply_patches()
    event = Event.parse_event(
        {
            "update_id": 1,
            "message_reaction": {
                "chat": {
                    "id": -100123456,
                    "type": "supergroup",
                    "title": "test",
                },
                "message_id": 7,
                "date": 1,
                "user": {"id": 42, "is_bot": False, "first_name": "Alice"},
                "old_reaction": [],
                "new_reaction": [{"type": "emoji", "emoji": "⭐"}],
            },
        }
    )

    assert isinstance(event, MessageReactionEvent)
    reaction = get_reaction_info(event)
    assert reaction is not None
    assert (reaction.face_id, reaction.is_add) == ("⭐", True)


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_fake_telegram_http_boundary_covers_required_apis(
    monkeypatch: pytest.MonkeyPatch,
):
    from hoshino.platform.telegram.bootstrap import apply_patches

    apply_patches()
    bot = _telegram_bot()
    requests = []

    async def fake_request(request):
        requests.append(request)
        endpoint = str(request.url).rsplit("/", 1)[-1]
        if endpoint == "getUpdates":
            result: Any = []
        elif endpoint == "getChatMember":
            result = {
                "status": "administrator",
                "user": {"id": 42, "is_bot": False, "first_name": "Alice"},
                "can_be_edited": False,
                "is_anonymous": False,
                "can_manage_chat": True,
                "can_delete_messages": True,
                "can_manage_video_chats": True,
                "can_restrict_members": True,
                "can_promote_members": False,
                "can_change_info": True,
                "can_invite_users": True,
                "can_post_stories": False,
                "can_edit_stories": False,
                "can_delete_stories": False,
            }
        elif endpoint == "sendMediaGroup":
            result = [_telegram_message(9)]
        elif endpoint == "forwardMessage":
            result = _telegram_message(10)
        else:
            result = _telegram_message(8)
        return Response(
            200, content=json.dumps({"ok": True, "result": result}).encode()
        )

    monkeypatch.setattr(bot.adapter, "request", fake_request)
    await bot.get_updates(timeout=0)
    await bot.get_chat_member(chat_id=-100123456, user_id=42)
    await bot.send_message(chat_id=-100123456, text="hello")
    await bot.send_media_group(
        chat_id=-100123456,
        media=[InputMediaPhoto(media="https://example.com/image.jpg")],
    )
    await bot.forward_message(chat_id=42, from_chat_id=-100123456, message_id=7)

    endpoints = [str(request.url).rsplit("/", 1)[-1] for request in requests]
    assert endpoints == [
        "getUpdates",
        "getChatMember",
        "sendMessage",
        "sendMediaGroup",
        "forwardMessage",
    ]
    allowed_updates = requests[0].json["allowed_updates"]
    assert "message_reaction" in json.loads(allowed_updates)


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_telegram_x_reaction_dispatches_historical_message(
    monkeypatch: pytest.MonkeyPatch,
):
    from nonebot.adapters.telegram import Event

    from hoshino.platform.telegram.bootstrap import apply_patches

    reaction_module = _x_module("reaction")
    apply_patches()
    bot = _telegram_bot()
    bot.config.superusers.add("telegram:42")
    event = Event.parse_event(
        {
            "update_id": 2,
            "message_reaction": {
                "chat": {
                    "id": -100123456,
                    "type": "supergroup",
                    "title": "test",
                },
                "message_id": 6856,
                "date": 1,
                "user": {"id": 42, "is_bot": False, "first_name": "Alice"},
                "old_reaction": [],
                "new_reaction": [{"type": "emoji", "emoji": "❤"}],
            },
        }
    )
    forwarded: list[tuple[int, int]] = []

    async def unexpected_claim(*args, **kwargs):
        pytest.fail("Telegram native forwarding must not access local reaction state")

    async def forward(bot_arg, target, reaction, reacted_message):
        forwarded.append((int(target.id), reaction.message_id))

    monkeypatch.setattr(reaction_module.store, "claim_reaction", unexpected_claim)
    monkeypatch.setattr(reaction_module, "forward_reacted_message", forward)
    monkeypatch.setattr(reaction_module.sv, "check_enabled", lambda scope: True)

    assert await reaction_module.x_reaction.matcher.permission(bot, event)
    await bot.handle_event(event)

    assert forwarded == [(42, 6856)]


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_x_reaction_filter_rejects_removed_reaction():
    from hoshino.platform import ReactionInfo

    assert not await _x_module("reaction").added_reaction(
        ReactionInfo("❤", False, 1, -100123456, 42, "emoji")
    )


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_x_reaction_forward_error_enters_runtime_error_queue(
    monkeypatch: pytest.MonkeyPatch,
):
    from hoshino.platform import ReactionInfo

    reaction_module = _x_module("reaction")
    bot = _telegram_bot()
    queued: list[tuple[str, Exception]] = []

    async def failed_forward(*args, **kwargs):
        raise RuntimeError("private chat unavailable")

    async def enqueue(subject: str, error: Exception) -> bool:
        queued.append((subject, error))
        return True

    monkeypatch.setattr(reaction_module, "forward_reacted_message", failed_forward)
    monkeypatch.setattr(reaction_module.runtime.errors, "enqueue", enqueue)

    await reaction_module.handle_x_reaction(
        bot,
        ReactionInfo("❤", True, 7, -100123456, 42, "emoji"),
    )

    assert len(queued) == 1
    assert queued[0][0] == "reaction-user-42"
    assert isinstance(queued[0][1], RuntimeError)


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_telegram_native_forward_and_private_403(
    monkeypatch: pytest.MonkeyPatch,
):
    from nonebot.adapters.telegram.exception import ActionFailed

    from hoshino.platform import ReactionInfo, forward_reacted_message, private_target

    bot = _telegram_bot()
    calls: list[dict[str, Any]] = []

    async def successful_forward(bot_arg, api, **kwargs):
        calls.append({"api": api, **kwargs})
        return _telegram_message(8)

    monkeypatch.setattr(bot.adapter, "_call_api", successful_forward)
    reaction = ReactionInfo("⭐", True, 7, -100123456, 42, "emoji")
    await forward_reacted_message(bot, private_target(42), reaction)
    assert calls[0]["api"] == "forward_message"
    assert calls[0]["chat_id"] == "42"
    assert calls[0]["from_chat_id"] == -100123456
    assert calls[0]["message_id"] == 7

    async def forbidden_forward(bot_arg, api, **kwargs):
        raise ActionFailed("Forbidden: bot can't initiate conversation with a user")

    monkeypatch.setattr(bot.adapter, "_call_api", forbidden_forward)
    with pytest.raises(ActionFailed, match="initiate conversation"):
        await forward_reacted_message(bot, private_target(42), reaction)


@pytest.mark.usefixtures("_nonebot_bootstrap")
@pytest.mark.parametrize("adapter_name", ("ob11", "milky"))
async def test_non_telegram_reaction_forward_rebuilds_locally(
    adapter_name: str,
    monkeypatch: pytest.MonkeyPatch,
):
    from hoshino.platform import (
        ReactionInfo,
        RetrievedMessage,
        forward_reacted_message,
        private_target,
    )
    from adapter_events import ob11_group_message
    from test_milky_adapter import _milky_group_message

    calls: list[tuple[str, dict[str, Any]]] = []
    if adapter_name == "ob11":
        bot, _ = ob11_group_message("ignored", to_me=False)

        async def fake_call_api(self, api: str, **data):
            calls.append((api, data))
            return {"message_id": 8}

        monkeypatch.setattr(type(bot), "call_api", fake_call_api)
    else:
        bot, _ = _milky_group_message("ignored", to_me=False)

        async def fake_private(self, *, user_id: int, message):
            calls.append(
                ("send_private_message", {"user_id": user_id, "message": message})
            )
            from nonebot.adapters.milky.model.api import MessageResponse

            return MessageResponse(message_seq=8, time=1)

        monkeypatch.setattr(type(bot), "send_private_message", fake_private)

    reaction = ReactionInfo("⭐", True, 7, 123456, 42, "emoji")
    source = RetrievedMessage(
        sender_id="10000",
        content=UniMessage.text("source message"),
        trusted_sender=True,
    )
    await forward_reacted_message(bot, private_target(42), reaction, source)

    if adapter_name == "ob11":
        assert calls[0][0] == "send_private_forward_msg"
        assert calls[0][1]["user_id"] == 42
    else:
        assert calls[0][0] == "send_private_message"
        assert calls[0][1]["user_id"] == 42
        assert calls[0][1]["message"][0].type == "forward"


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_x_store_cursor_outbox_and_restart(tmp_path: Path):
    db = _x_module("db")
    post_module = _x_module("post")
    store = db.XStore(tmp_path / "x.db")
    await store.add_subscription(
        scope_key="telegram:-1",
        platform="telegram",
        group_id=-1,
        target_data='{"id":"-1","parent_id":"","channel":false,"private":false,"extra":{},"scope":null,"adapter":null,"platforms":null}',
        username="alice",
        name="alice",
    )
    post = post_module.XPost(uid="alice", id="101", content="hello")
    assert await store.enqueue_posts("alice", [post]) == 1
    assert await store.get_cursor("alice") == 101

    restarted = db.XStore(tmp_path / "x.db")
    due = await restarted.due_outbox()
    assert len(due) == 1
    await restarted.mark_failed(due[0].id, 0, "temporary")
    retried = await restarted.due_outbox()
    assert retried[0].attempts == 1
    await restarted.mark_sent(retried[0].id)
    assert await restarted.due_outbox() == []


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_x_workflow_first_fetch_cookie_redaction_and_429(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    client_module = _x_module("client")
    config_module = _x_module("config")
    db = _x_module("db")
    runtime_module = _x_module("runtime")
    store = db.XStore(tmp_path / "x.db")
    await store.add_subscription(
        scope_key="telegram:-1",
        platform="telegram",
        group_id=-1,
        target_data="{}",
        username="alice",
        name="alice",
    )
    settings = replace(
        config_module.XSettings(),
        rate_limit_requests=1000,
        rate_limit_window_seconds=1,
        hot_interval_seconds=0,
        cold_interval_seconds=0,
    )

    logger = RecordingLogger()
    monkeypatch.setattr(runtime_module.sv, "logger", logger)
    monkeypatch.setattr(runtime_module.sv, "get_config", lambda: settings)
    monkeypatch.setattr(
        runtime_module,
        "get_cookies_with_ts",
        lambda name: _async_result(({"ct0": "secret-ct0"}, time.time())),
    )
    runtime = runtime_module.XRuntime(store)
    await runtime.bootstrap()
    assert not await runtime.fetch_next_update()
    assert logger.warnings == ["X cookie is missing required fields: auth_token"]
    assert "secret-ct0" not in logger.warnings[0]

    class LimitedClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def resolve_user_id(self, username):
            raise client_module.XRateLimited("UserByScreenName", 9999999999)

    monkeypatch.setattr(
        runtime_module,
        "get_cookies_with_ts",
        lambda name: _async_result(
            ({"auth_token": "secret-auth", "ct0": "secret-ct0"}, time.time())
        ),
    )
    monkeypatch.setattr(runtime_module, "XClient", LimitedClient)
    assert not await runtime.fetch_next_update()
    state = await store.get_account_state("alice")
    assert state.retry_at == 9999999999


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_x_workflow_rejects_expired_cookie_without_logging_values(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    db = _x_module("db")
    runtime_module = _x_module("runtime")
    store = db.XStore(tmp_path / "x.db")
    await store.add_subscription(
        scope_key="telegram:-1",
        platform="telegram",
        group_id=-1,
        target_data="{}",
        username="alice",
        name="alice",
    )
    logger = RecordingLogger()
    monkeypatch.setattr(runtime_module.sv, "logger", logger)
    monkeypatch.setattr(
        runtime_module,
        "get_cookies_with_ts",
        lambda name: _async_result(
            ({"auth_token": "auth-value", "ct0": "ct0-value"}, 1)
        ),
    )
    runtime = runtime_module.XRuntime(store)
    await runtime.bootstrap()

    assert not await runtime.fetch_next_update()
    assert logger.warnings == ["X cookie is expired; polling is paused"]
    assert "auth-value" not in logger.warnings[0]
    assert "ct0-value" not in logger.warnings[0]


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_x_workflow_first_fetch_only_sets_cursor_then_enqueues(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    config_module = _x_module("config")
    db = _x_module("db")
    runtime_module = _x_module("runtime")
    store = db.XStore(tmp_path / "x.db")
    await store.add_subscription(
        scope_key="telegram:-1",
        platform="telegram",
        group_id=-1,
        target_data="{}",
        username="alice",
        name="alice",
    )
    tweets = [_tweet(100)]

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def resolve_user_id(self, username):
            return 1

        async def fetch_recent(self, user_id, limit):
            return list(tweets)

    class FakeMedia:
        async def persist(self, post, max_media):
            return post

        def pop_errors(self):
            return []

    logger = RecordingLogger()
    monkeypatch.setattr(runtime_module.sv, "logger", logger)
    monkeypatch.setattr(
        runtime_module,
        "get_cookies_with_ts",
        lambda name: _async_result(({"auth_token": "a", "ct0": "c"}, time.time())),
    )
    settings = replace(
        config_module.XSettings(),
        rate_limit_requests=1000,
        rate_limit_window_seconds=1,
    )
    monkeypatch.setattr(runtime_module.sv, "get_config", lambda: settings)
    runtime = runtime_module.XRuntime(store)
    monkeypatch.setattr(runtime_module, "XClient", FakeClient)
    runtime.fetch_mainline.media_store = FakeMedia()

    assert await runtime.fetch_mainline.fetch("alice")
    assert await store.get_cursor("alice") == 100
    assert await store.due_outbox() == []

    tweets.append(_tweet(101, content="new"))
    monkeypatch.setattr(
        store,
        "acquire_rate_permit",
        lambda *args, **kwargs: _async_result(db.RatePermit(True, 0)),
    )
    assert await runtime.fetch_mainline.fetch("alice")
    due = await store.due_outbox()
    assert [item.post.id for item in due] == ["101"]


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_x_account_failure_does_not_block_next_account(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    config_module = _x_module("config")
    db = _x_module("db")
    runtime_module = _x_module("runtime")
    store = db.XStore(tmp_path / "x.db")
    for username in ("alice", "bob"):
        await store.add_subscription(
            scope_key="telegram:-1",
            platform="telegram",
            group_id=-1,
            target_data="{}",
            username=username,
            name=username,
        )

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def resolve_user_id(self, username):
            if username == "alice":
                raise RuntimeError("alice failed")
            return 2

        async def fetch_recent(self, user_id, limit):
            return []

    logger = RecordingLogger()
    monkeypatch.setattr(runtime_module.sv, "logger", logger)
    monkeypatch.setattr(
        runtime_module,
        "get_cookies_with_ts",
        lambda name: _async_result(({"auth_token": "a", "ct0": "c"}, time.time())),
    )
    monkeypatch.setattr(
        store,
        "acquire_rate_permit",
        lambda *args, **kwargs: _async_result(db.RatePermit(True, 0)),
    )
    monkeypatch.setattr(runtime_module.sv, "get_config", config_module.XSettings)
    runtime = runtime_module.XRuntime(store)
    monkeypatch.setattr(runtime_module, "XClient", FakeClient)

    assert not await runtime.fetch_mainline.fetch("alice")
    assert await runtime.fetch_mainline.fetch("bob")


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_x_error_queue_notifies_generic_error_without_removing_account(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    db = _x_module("db")
    runtime_module = _x_module("runtime")
    store = db.XStore(tmp_path / "x.db")
    await store.add_subscription(
        scope_key="telegram:-1",
        platform="telegram",
        group_id=-1,
        target_data="{}",
        username="alice",
        name="alice",
    )
    uid_manager = runtime_module.UIDManager()
    await uid_manager.init(["alice"], min_interval=0, cold_min_interval=0)
    notifications: list[str] = []
    bot = object()
    monkeypatch.setattr(runtime_module.nonebot, "get_bots", lambda: {"bot": bot})
    monkeypatch.setattr(runtime_module, "COOKIE_WARNING_INTERVAL", 0)
    monkeypatch.setattr(
        runtime_module,
        "send_to_superuser",
        lambda actual_bot, message: _record_async(
            notifications, message if actual_bot is bot else "wrong bot"
        ),
    )
    queue = runtime_module.XErrorQueue(store, uid_manager)

    assert await queue.enqueue("alice", RuntimeError("upstream failed"))
    assert await queue.process_next()

    assert await store.usernames() == ["alice"]
    assert uid_manager.get_count() == 1
    assert notifications == ["X 运行异常: @alice RuntimeError"]


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_x_user_not_found_is_removed_only_when_error_queue_consumes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    client_module = _x_module("client")
    config_module = _x_module("config")
    db = _x_module("db")
    runtime_module = _x_module("runtime")
    store = db.XStore(tmp_path / "x.db")
    for scope_key in ("telegram:-1", "milky:2"):
        await store.add_subscription(
            scope_key=scope_key,
            platform=scope_key.split(":", 1)[0],
            group_id=int(scope_key.split(":", 1)[1]),
            target_data="{}",
            username="alice",
            name="alice",
        )

    class MissingUserClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def resolve_user_id(self, username):
            raise client_module.XUserNotFound("missing")

    monkeypatch.setattr(
        runtime_module,
        "get_cookies_with_ts",
        lambda name: _async_result(({"auth_token": "a", "ct0": "c"}, time.time())),
    )
    monkeypatch.setattr(
        store,
        "acquire_rate_permit",
        lambda *args, **kwargs: _async_result(db.RatePermit(True, 0)),
    )
    notifications: list[str] = []
    bot = object()
    monkeypatch.setattr(runtime_module.nonebot, "get_bots", lambda: {"bot": bot})
    monkeypatch.setattr(runtime_module.sv, "get_config", config_module.XSettings)
    monkeypatch.setattr(
        runtime_module,
        "send_to_superuser",
        lambda actual_bot, message: _record_async(
            notifications, message if actual_bot is bot else "wrong bot"
        ),
    )
    runtime = runtime_module.XRuntime(store)
    monkeypatch.setattr(runtime_module, "XClient", MissingUserClient)
    await runtime.bootstrap()

    assert await runtime.fetch_mainline.fetch("alice")
    assert await store.usernames() == ["alice"]
    assert runtime.uid_manager.get_count() == 1

    assert await runtime.errors.process_next()

    assert await store.usernames() == []
    assert runtime.uid_manager.get_count() == 0
    assert notifications == ["X 账号不存在，已自动删除订阅: @alice, 共 2 条"]


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_x_user_not_found_notification_retry_does_not_repeat_deletion(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    client_module = _x_module("client")
    db = _x_module("db")
    runtime_module = _x_module("runtime")
    store = db.XStore(tmp_path / "x.db")
    await store.add_subscription(
        scope_key="telegram:-1",
        platform="telegram",
        group_id=-1,
        target_data="{}",
        username="alice",
        name="alice",
    )
    uid_manager = runtime_module.UIDManager()
    await uid_manager.init(["alice"], min_interval=0, cold_min_interval=0)
    sent: list[str] = []
    attempts = 0
    bot = object()
    monkeypatch.setattr(runtime_module.nonebot, "get_bots", lambda: {"bot": bot})

    async def flaky_sender(actual_bot, message: str) -> None:
        nonlocal attempts
        assert actual_bot is bot
        attempts += 1
        if attempts == 1:
            raise RuntimeError("notification failed")
        sent.append(message)

    remove_calls = 0
    original_remove = store.remove_account

    async def counted_remove(username: str) -> int:
        nonlocal remove_calls
        remove_calls += 1
        return await original_remove(username)

    monkeypatch.setattr(store, "remove_account", counted_remove)
    monkeypatch.setattr(runtime_module, "COOKIE_WARNING_INTERVAL", 0)
    monkeypatch.setattr(runtime_module, "send_to_superuser", flaky_sender)
    monkeypatch.setattr(runtime_module.sv, "logger", RecordingLogger())
    queue = runtime_module.XErrorQueue(store, uid_manager)
    await queue.enqueue("alice", client_module.XUserNotFound("missing"))

    assert not await queue.process_next()
    assert await queue.process_next()

    assert remove_calls == 1
    assert sent == ["X 账号不存在，已自动删除订阅: @alice, 共 1 条"]


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_x_media_download_error_enters_runtime_error_queue(
    monkeypatch: pytest.MonkeyPatch,
):
    media_module = _x_module("media")
    post_module = _x_module("post")
    media_store = media_module.XMediaStore()
    post = post_module.XPost(uid="alice", id="101", content="media")

    def failed_stream(*args, **kwargs):
        raise httpx.ConnectError("offline")

    monkeypatch.setattr(media_store.client, "stream", failed_stream)
    try:
        result = await media_store._download(
            post, "https://img.invalid/image.jpg", False
        )
    finally:
        await media_store.close()

    assert result is None
    errors = media_store.pop_errors()
    assert len(errors) == 1
    assert errors[0][0] == "alice"
    assert isinstance(errors[0][1], httpx.ConnectError)


async def _async_result(value):
    return value


async def _record_async(items: list, value) -> None:
    items.append(value)
