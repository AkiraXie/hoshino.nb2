"""X fetch and dispatch mainlines."""

from __future__ import annotations

import asyncio
import hashlib
import time
from dataclasses import dataclass

import nonebot
from nonebot.adapters import Bot
from twscrape.models import Tweet

from hoshino.content import PostQueue, UIDManager
from hoshino.content.dispatch import retry_delay
from hoshino.platform import (
    load_target,
    platform_key,
    send_to_superuser,
    send_to_target,
)
from hoshino.util.cookies import get_cookies_with_ts

from .client import (
    LIST_TWEETS_ENDPOINT,
    USER_LOOKUP_ENDPOINT,
    USER_TWEETS_ENDPOINT,
    XAuthenticationError,
    XClient,
    XRateLimited,
    XUserNotFound,
)
from .config import XSettings
from .db import OutboxItem, XStore, parse_list_source_key
from .media import XMediaStore
from .post import XPost
from .sv import sv


COOKIE_NAME = "x"
REQUIRED_COOKIES = ("auth_token", "ct0")
COOKIE_WARNING_INTERVAL = 1800.0
COOKIE_MAX_AGE = 7 * 86400.0


class XCredentialError(RuntimeError):
    pass


class XCookieMissing(XCredentialError):
    def __init__(self, fields: tuple[str, ...]) -> None:
        super().__init__("X cookie is incomplete")
        self.fields = fields


class XCookieExpired(XCredentialError):
    pass


@dataclass(slots=True)
class XErrorTask:
    username: str
    error: Exception
    deleted_subscriptions: int | None = None


class XErrorQueue:
    def __init__(
        self,
        store: XStore,
        uid_manager: UIDManager,
    ) -> None:
        self.store = store
        self.uid_manager = uid_manager
        self.queue: asyncio.Queue[XErrorTask] = asyncio.Queue()
        self._pending: set[tuple[str, str]] = set()
        self._last_sent: dict[tuple[str, str], float] = {}

    async def enqueue(self, username: str, error: Exception) -> bool:
        task = XErrorTask(username, error)
        key = self._key(task)
        now = time.time()
        if (
            key in self._pending
            or now - self._last_sent.get(key, 0) < COOKIE_WARNING_INTERVAL
        ):
            return False
        self._pending.add(key)
        await self.queue.put(task)
        return True

    async def process_next(self) -> bool:
        try:
            task = self.queue.get_nowait()
        except asyncio.QueueEmpty:
            return False
        key = self._key(task)
        try:
            message = await self._process(task)
            bots = list(nonebot.get_bots().values())
            if not bots:
                bots = [nonebot.get_bot()]
            for bot in bots:
                await send_to_superuser(bot, message)
        except asyncio.CancelledError:
            await self.queue.put(task)
            raise
        except Exception as exc:
            await self.queue.put(task)
            sv.logger.error(
                f"X error queue processing failed: {type(exc).__name__}",
                exception=False,
            )
            return False
        else:
            self._pending.discard(key)
            self._last_sent[key] = time.time()
            return True
        finally:
            self.queue.task_done()

    async def _process(self, task: XErrorTask) -> str:
        if isinstance(task.error, XUserNotFound):
            if task.deleted_subscriptions is None:
                task.deleted_subscriptions = await self.store.remove_account(
                    task.username
                )
                await self.uid_manager.remove_uid(task.username, lambda _: False)
            sv.logger.warning(
                f"X account @{task.username} was not found; removed "
                f"{task.deleted_subscriptions} subscription(s)"
            )
            return (
                f"X 账号不存在，已自动删除订阅: @{task.username}, "
                f"共 {task.deleted_subscriptions} 条"
            )
        if isinstance(task.error, XCookieMissing):
            return f"X cookie 缺少必要字段: {', '.join(task.error.fields)}"
        if isinstance(task.error, XCookieExpired):
            return "X cookie 已过期，抓取已暂停"
        if isinstance(task.error, XRateLimited):
            return f"X 接口触发限流: {task.error.endpoint}"
        return f"X 运行异常: @{task.username} {type(task.error).__name__}"

    @staticmethod
    def _key(task: XErrorTask) -> tuple[str, str]:
        error_name = type(task.error).__name__
        if isinstance(task.error, XCredentialError):
            return "credentials", error_name
        if isinstance(task.error, XRateLimited):
            return task.error.endpoint, error_name
        return task.username, error_name


def _cookie_fingerprint(cookies: dict[str, str]) -> str:
    """Stable identity of a credential set, without retaining the raw values."""
    payload = ";".join(f"{key}={value}" for key, value in sorted(cookies.items()))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class CredentialProvider:
    """Load and validate X cookies without exposing their values.

    Remembers which credential has already proven expired/unusable so polling
    can skip it silently instead of re-requesting and re-notifying forever.
    """

    def __init__(self) -> None:
        self._last_missing_warning: float = 0.0
        self._expired_fingerprint: str | None = None

    async def load(self, now: float | None = None) -> tuple[dict[str, str], float]:
        checked_at = time.time() if now is None else now
        cookies, updated_at = await get_cookies_with_ts(COOKIE_NAME)
        missing = tuple(field for field in REQUIRED_COOKIES if not cookies.get(field))
        if missing:
            if checked_at - self._last_missing_warning >= COOKIE_WARNING_INTERVAL:
                sv.logger.warning(
                    f"X cookie is missing required fields: {', '.join(missing)}"
                )
                self._last_missing_warning = checked_at
            raise XCookieMissing(missing)
        return cookies, updated_at

    def is_known_expired(self, cookies: dict[str, str]) -> bool:
        return self._expired_fingerprint == _cookie_fingerprint(cookies)

    def mark_expired(self, cookies: dict[str, str]) -> None:
        fingerprint = _cookie_fingerprint(cookies)
        if self._expired_fingerprint != fingerprint:
            sv.logger.warning("X cookie is expired; polling is paused")
        self._expired_fingerprint = fingerprint


def _source_label(source: str) -> str:
    """Human-readable label for logs: ``@user`` or ``list:<id>``."""
    return source if parse_list_source_key(source) is not None else f"@{source}"


class FetchMainline:
    def __init__(
        self,
        store: XStore,
        uid_manager: UIDManager,
        credentials: CredentialProvider,
        errors: XErrorQueue,
    ) -> None:
        self.store = store
        self.uid_manager = uid_manager
        self.credentials = credentials
        self.errors = errors
        self.media_store: XMediaStore | None = None

    async def fetch(self, source: str) -> bool:
        settings = sv.get_config()
        state = await self.store.get_account_state(source)
        now = time.time()
        if state.retry_at > now:
            return False
        try:
            cookies, updated_at = await self.credentials.load(now)
        except XCredentialError as exc:
            await self.errors.enqueue(source, exc)
            return False

        # Skip a credential we already proved expired/unusable. Once the user
        # replaces it the fingerprint changes and polling resumes by itself.
        if self.credentials.is_known_expired(cookies):
            return False
        if updated_at <= 0 or now - updated_at > COOKIE_MAX_AGE:
            self.credentials.mark_expired(cookies)
            await self.errors.enqueue(source, XCookieExpired("X cookie is expired"))
            return False

        label = _source_label(source)
        try:
            tweets = await self._fetch_tweets(source, state.user_id, cookies, settings)
        except XRateLimited as exc:
            await self.store.set_rate_cooldown(exc.endpoint, exc.retry_at)
            await self.store.defer_poll(source, exc.retry_at, type(exc).__name__)
            sv.logger.warning(f"X rate limit reached for {label} on {exc.endpoint}")
            await self.errors.enqueue(source, exc)
            return False
        except XUserNotFound as exc:
            await self.errors.enqueue(source, exc)
            return True
        except XAuthenticationError as exc:
            self.credentials.mark_expired(cookies)
            await self.errors.enqueue(
                source, XCookieExpired(str(exc) or "X credential is inactive")
            )
            return False
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            delay = retry_delay(
                state.failures, settings.retry_base_seconds, settings.retry_max_seconds
            )
            await self.store.defer_poll(
                source, now + delay, f"{type(exc).__name__}: {exc}"
            )
            sv.logger.error(
                f"X polling failed for {label}: {type(exc).__name__}",
                exception=False,
            )
            await self.errors.enqueue(source, exc)
            return False

        if tweets is None:
            return False
        await self._persist_updates(source, tweets, state.last_posted_at, now, settings)
        return True

    async def _fetch_tweets(
        self,
        source: str,
        user_id: int | None,
        cookies: dict[str, str],
        settings: XSettings,
    ) -> list[Tweet] | None:
        list_id = parse_list_source_key(source)
        async with XClient(cookies) as client:
            if list_id is not None:
                permit = await self.store.acquire_rate_permit(
                    LIST_TWEETS_ENDPOINT, settings.rate_interval
                )
                if not permit.allowed:
                    return None
                return await asyncio.wait_for(
                    client.fetch_list_recent(list_id, settings.max_tweets_per_account),
                    timeout=settings.request_timeout_seconds,
                )
            if user_id is None:
                permit = await self.store.acquire_rate_permit(
                    USER_LOOKUP_ENDPOINT, settings.rate_interval
                )
                if not permit.allowed:
                    return None
                user_id = await asyncio.wait_for(
                    client.resolve_user_id(source),
                    timeout=settings.request_timeout_seconds,
                )
                await self.store.set_user_id(source, user_id)
            permit = await self.store.acquire_rate_permit(
                USER_TWEETS_ENDPOINT, settings.rate_interval
            )
            if not permit.allowed:
                return None
            return await asyncio.wait_for(
                client.fetch_recent(user_id, settings.max_tweets_per_account),
                timeout=settings.request_timeout_seconds,
            )

    async def _persist_updates(
        self,
        source: str,
        tweets: list[Tweet],
        previous_posted_at: float,
        now: float,
        settings: XSettings,
    ) -> None:
        if not tweets:
            await self.store.complete_poll(source)
            return
        cursor = await self.store.get_cursor(source)
        newest_id = max(tweet.id for tweet in tweets)
        if cursor is None:
            await self.store.set_cursor(source, newest_id)
            await self.store.complete_poll(source)
            return

        posts = [XPost.from_tweet(tweet) for tweet in tweets if tweet.id > cursor]
        posts.sort(key=lambda post: int(post.id))
        if posts:
            media_store = self._media_store()
            for post in posts:
                await media_store.persist(post, settings.max_media_per_tweet)
                await media_store.write_metadata(post)
                for uid, error in media_store.pop_errors():
                    await self.errors.enqueue(uid, error)
            list_id = parse_list_source_key(source)
            if list_id is not None:
                await self.store.enqueue_list_posts(list_id, posts)
            else:
                await self.store.enqueue_posts(source, posts)
            sv.logger.info(
                f"Fetched {len(posts)} X update(s) for {_source_label(source)}"
            )
        else:
            await self.store.set_cursor(source, newest_id)

        latest_timestamp = max((post.timestamp for post in posts), default=0.0)
        await self.store.complete_poll(source, last_posted_at=latest_timestamp)
        if latest_timestamp and now - latest_timestamp < settings.cold_after_seconds:
            await self.uid_manager.unmark_cold(source)
        elif (
            previous_posted_at
            and now - previous_posted_at >= settings.cold_after_seconds
        ):
            await self.uid_manager.mark_cold(source)

    def _media_store(self) -> XMediaStore:
        if self.media_store is None:
            self.media_store = XMediaStore()
        return self.media_store

    async def close(self) -> None:
        if self.media_store is not None:
            await self.media_store.close()
            self.media_store = None


# Platform API rejections that can never succeed on retry, matched against the
# lower-cased ActionFailed reason. Network timeouts, rate limits ("Too Many
# Requests") and 5xx responses deliberately do NOT match — those stay transient.
_PERMANENT_DELIVERY_ERROR_MARKERS = (
    # Content the platform refuses outright, no matter when we retry it.
    "is too long",
    "message text is empty",
    "can't parse entities",
    # The target is gone for good, or the bot can no longer post there.
    "chat not found",
    "user not found",
    "bot was kicked",
    "bot is not a member",
    "not a member of the group",
    "chat was deleted",
    "group is deactivated",
    "user is deactivated",
    "not enough rights",
    "have no rights",
)


def is_permanent_delivery_error(exc: Exception) -> bool:
    """Return True when a delivery error can never succeed and must not retry.

    Only adapter API rejections (``ActionFailed``, matched by class name so this
    stays adapter-neutral) carry a definitive server-side reason; anything else
    (timeouts, connection errors, disabled service) is treated as transient.
    """
    if type(exc).__name__ != "ActionFailed":
        return False
    reason = str(exc).lower()
    return any(marker in reason for marker in _PERMANENT_DELIVERY_ERROR_MARKERS)


class DeliveryExecutor:
    async def send(self, item: OutboxItem) -> None:
        if not sv.check_enabled(item.scope_key):
            raise RuntimeError(f"X service is disabled for {item.scope_key}")
        bot = self._select_bot(item.platform)
        target = load_target(item.target_data)
        post_message = await item.post.get_message()
        for message in item.post.render_message(post_message):
            await send_to_target(bot, target, message)

    @staticmethod
    def _select_bot(platform: str) -> Bot:
        for bot in nonebot.get_bots().values():
            if platform_key(bot) == platform:
                return bot
        raise RuntimeError(f"No connected {platform} bot")


class DispatchMainline:
    def __init__(
        self,
        store: XStore,
        errors: XErrorQueue,
    ) -> None:
        self.store = store
        self.errors = errors
        self.queue = PostQueue[OutboxItem]()
        self.executor = DeliveryExecutor()

    async def dispatch_due(self, limit: int = 10) -> int:
        for item in await self.store.due_outbox(limit):
            self.queue.put(item)
        sent = 0
        while item := self.queue.get():
            try:
                await self.executor.send(item)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                await self._handle_failure(item, exc)
            else:
                await self.store.mark_sent(item.id)
                sent += 1
            finally:
                self.queue.remove(item)
        return sent

    async def _handle_failure(self, item: OutboxItem, exc: Exception) -> None:
        settings = sv.get_config()
        error_text = f"{type(exc).__name__}: {exc}"
        attempt_number = item.attempts + 1
        if is_permanent_delivery_error(exc):
            # The platform will never accept this item; stop immediately instead
            # of burning retries (and superuser notifications) forever.
            await self.store.mark_dead(item.id, error_text)
            sv.logger.error(
                f"X delivery gave up on outbox {item.id} "
                f"(permanent error): {error_text}",
                exception=False,
            )
        elif attempt_number >= settings.delivery_max_attempts:
            await self.store.mark_dead(item.id, error_text)
            sv.logger.error(
                f"X delivery gave up on outbox {item.id} "
                f"after {attempt_number} attempts: {error_text}",
                exception=False,
            )
        else:
            retry_at = time.time() + retry_delay(
                item.attempts,
                settings.delivery_retry_base_seconds,
                settings.delivery_retry_max_seconds,
            )
            await self.store.mark_failed(item.id, retry_at, error_text)
            sv.logger.error(
                f"X delivery failed for outbox {item.id}: {type(exc).__name__}",
                exception=False,
            )
        await self.errors.enqueue(item.post.uid, exc)


class XRuntime:
    def __init__(self, store: XStore) -> None:
        self.store = store
        self.uid_manager = UIDManager()
        self.credentials = CredentialProvider()
        self.errors = XErrorQueue(store, self.uid_manager)
        self.fetch_mainline = FetchMainline(
            store,
            self.uid_manager,
            self.credentials,
            self.errors,
        )
        self.dispatch_mainline = DispatchMainline(store, self.errors)

    async def bootstrap(self) -> None:
        await self.store.initialize()
        await self.refresh_accounts()

    async def shutdown(self) -> None:
        await self.fetch_mainline.close()

    async def refresh_accounts(self) -> None:
        settings = sv.get_config()
        sources = [*await self.store.usernames(), *await self.store.list_source_keys()]
        await self.uid_manager.init(
            sources,
            settings.hot_interval_seconds,
            settings.cold_interval_seconds,
        )

    async def add_account(self, source: str) -> None:
        await self.uid_manager.add_uid(source.lower())

    async def fetch_next_update(self) -> bool:
        source = await self.uid_manager.get_next_uid()
        if source is None:
            return False
        success = False
        try:
            success = await self.fetch_mainline.fetch(source)
            return success
        finally:
            await self.uid_manager.finish_processing(source, success)

    async def dispatch_pending(self, limit: int = 10) -> int:
        await self.errors.process_next()
        return await self.dispatch_mainline.dispatch_due(limit)


store = XStore()
runtime = XRuntime(store)


__all__ = [
    "COOKIE_NAME",
    "REQUIRED_COOKIES",
    "CredentialProvider",
    "DeliveryExecutor",
    "DispatchMainline",
    "FetchMainline",
    "XErrorQueue",
    "XErrorTask",
    "XCookieExpired",
    "XCookieMissing",
    "XRuntime",
    "is_permanent_delivery_error",
    "runtime",
    "store",
]
