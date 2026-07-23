"""X fetch and dispatch mainlines."""

from __future__ import annotations

import asyncio
import random
import time
from dataclasses import dataclass

import nonebot
from nonebot.adapters import Bot
from twscrape.models import Tweet

from hoshino.content import PostQueue, UIDManager
from hoshino.platform import load_target, platform_key, send_to_target
from hoshino.util.cookies import get_cookies_with_ts
from hoshino.util.message import send_to_superuser

from .client import (
    USER_LOOKUP_ENDPOINT,
    USER_TWEETS_ENDPOINT,
    XAuthenticationError,
    XClient,
    XRateLimited,
    XUserNotFound,
)
from .config import XSettings
from .db import OutboxItem, XStore
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
            await send_to_superuser(message)
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


class CredentialProvider:
    """Load and validate X cookies without exposing their values."""

    def __init__(self) -> None:
        self._last_warning: tuple[tuple[str, ...], float] | None = None

    async def load(self, now: float | None = None) -> dict[str, str]:
        checked_at = time.time() if now is None else now
        cookies, updated_at = await get_cookies_with_ts(COOKIE_NAME)
        missing = tuple(field for field in REQUIRED_COOKIES if not cookies.get(field))
        if missing:
            self._warn(missing, checked_at)
            raise XCookieMissing(missing)
        if updated_at <= 0 or checked_at - updated_at > COOKIE_MAX_AGE:
            self._warn(("expired",), checked_at)
            raise XCookieExpired("X cookie is expired")
        self._last_warning = None
        return cookies

    def _warn(self, state: tuple[str, ...], now: float) -> None:
        if (
            self._last_warning is not None
            and self._last_warning[0] == state
            and now - self._last_warning[1] < COOKIE_WARNING_INTERVAL
        ):
            return
        if state == ("expired",):
            sv.logger.warning("X cookie is expired; polling is paused")
        else:
            sv.logger.warning(
                f"X cookie is missing required fields: {', '.join(state)}"
            )
        self._last_warning = (state, now)


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

    async def fetch(self, username: str) -> bool:
        settings = sv.get_config()
        state = await self.store.get_account_state(username)
        now = time.time()
        if state.retry_at > now:
            return False
        try:
            cookies = await self.credentials.load(now)
        except XCredentialError as exc:
            await self.errors.enqueue(username, exc)
            return False

        try:
            tweets = await self._fetch_tweets(
                username, state.user_id, cookies, settings
            )
        except XRateLimited as exc:
            await self.store.set_rate_cooldown(exc.endpoint, exc.retry_at)
            await self.store.defer_poll(username, exc.retry_at, type(exc).__name__)
            sv.logger.warning(f"X rate limit reached for @{username} on {exc.endpoint}")
            await self.errors.enqueue(username, exc)
            return False
        except XUserNotFound as exc:
            await self.errors.enqueue(username, exc)
            return True
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            delay = retry_delay(
                state.failures, settings.retry_base_seconds, settings.retry_max_seconds
            )
            await self.store.defer_poll(
                username, now + delay, f"{type(exc).__name__}: {exc}"
            )
            message = f"X polling failed for @{username}: {type(exc).__name__}"
            if isinstance(exc, XAuthenticationError):
                sv.logger.warning(message)
            else:
                sv.logger.error(message, exception=False)
            await self.errors.enqueue(username, exc)
            return False

        if tweets is None:
            return False
        await self._persist_updates(
            username, tweets, state.last_posted_at, now, settings
        )
        return True

    async def _fetch_tweets(
        self,
        username: str,
        user_id: int | None,
        cookies: dict[str, str],
        settings: XSettings,
    ) -> list[Tweet] | None:
        async with XClient(cookies) as client:
            if user_id is None:
                permit = await self.store.acquire_rate_permit(
                    USER_LOOKUP_ENDPOINT, settings.rate_interval
                )
                if not permit.allowed:
                    return None
                user_id = await asyncio.wait_for(
                    client.resolve_user_id(username),
                    timeout=settings.request_timeout_seconds,
                )
                await self.store.set_user_id(username, user_id)
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
        username: str,
        tweets: list[Tweet],
        previous_posted_at: float,
        now: float,
        settings: XSettings,
    ) -> None:
        if not tweets:
            await self.store.complete_poll(username)
            return
        cursor = await self.store.get_cursor(username)
        newest_id = max(tweet.id for tweet in tweets)
        if cursor is None:
            await self.store.set_cursor(username, newest_id)
            await self.store.complete_poll(username)
            return

        posts = [XPost.from_tweet(tweet) for tweet in tweets if tweet.id > cursor]
        posts.sort(key=lambda post: int(post.id))
        if posts:
            media_store = self._media_store()
            for post in posts:
                await media_store.persist(post, settings.max_media_per_tweet)
                for username, error in media_store.pop_errors():
                    await self.errors.enqueue(username, error)
            await self.store.enqueue_posts(username, posts)
            sv.logger.info(f"Fetched {len(posts)} X update(s) for @{username}")
        else:
            await self.store.set_cursor(username, newest_id)

        latest_timestamp = max((post.timestamp for post in posts), default=0.0)
        await self.store.complete_poll(username, last_posted_at=latest_timestamp)
        if latest_timestamp and now - latest_timestamp < settings.cold_after_seconds:
            await self.uid_manager.unmark_cold(username)
        elif (
            previous_posted_at
            and now - previous_posted_at >= settings.cold_after_seconds
        ):
            await self.uid_manager.mark_cold(username)

    def _media_store(self) -> XMediaStore:
        if self.media_store is None:
            self.media_store = XMediaStore()
        return self.media_store

    async def close(self) -> None:
        if self.media_store is not None:
            await self.media_store.close()
            self.media_store = None


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
                settings = sv.get_config()
                retry_at = time.time() + retry_delay(
                    item.attempts,
                    settings.delivery_retry_base_seconds,
                    settings.delivery_retry_max_seconds,
                )
                await self.store.mark_failed(
                    item.id, retry_at, f"{type(exc).__name__}: {exc}"
                )
                sv.logger.error(
                    f"X delivery failed for outbox {item.id}: {type(exc).__name__}",
                    exception=False,
                )
                await self.errors.enqueue(item.post.uid, exc)
            else:
                await self.store.mark_sent(item.id)
                sent += 1
            finally:
                self.queue.remove(item)
        return sent


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
        await self.uid_manager.init(
            await self.store.usernames(),
            settings.hot_interval_seconds,
            settings.cold_interval_seconds,
        )

    async def add_account(self, username: str) -> None:
        await self.uid_manager.add_uid(username.lower())

    async def fetch_next_update(self) -> bool:
        username = await self.uid_manager.get_next_uid()
        if username is None:
            return False
        success = False
        try:
            success = await self.fetch_mainline.fetch(username)
            return success
        finally:
            await self.uid_manager.finish_processing(username, success)

    async def dispatch_pending(self, limit: int = 10) -> int:
        await self.errors.process_next()
        return await self.dispatch_mainline.dispatch_due(limit)


def retry_delay(attempts: int, base: float, maximum: float) -> float:
    base = max(1.0, base)
    maximum = max(base, maximum)
    delay = min(maximum, base * (2 ** min(max(0, attempts), 10)))
    return delay + random.uniform(0, min(delay * 0.2, 30.0))


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
    "runtime",
    "store",
]
