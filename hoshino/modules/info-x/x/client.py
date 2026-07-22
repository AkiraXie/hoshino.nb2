"""Persistent, rate-limit-aware twscrape client."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path
from twscrape import API, NoAccountError, gather
from twscrape.models import Tweet
from twscrape.utils import parse_cookies

from hoshino import db_dir


USER_LOOKUP_ENDPOINT = "UserByScreenName"
USER_TWEETS_ENDPOINT = "UserTweets"


class XRateLimited(RuntimeError):
    def __init__(self, endpoint: str, retry_at: float):
        super().__init__(f"X endpoint {endpoint} is rate limited")
        self.endpoint = endpoint
        self.retry_at = retry_at


class XAuthenticationError(RuntimeError):
    pass


class XUserNotFound(RuntimeError):
    pass


class XUpstreamError(RuntimeError):
    pass


class XClient:
    def __init__(
        self,
        cookies: dict[str, str],
        *,
        proxy: str | None = None,
        db_path: Path | None = None,
    ) -> None:
        self.cookies = cookies
        self.proxy = proxy
        self.db_path = db_path or (db_dir / "x_twscrape.db")
        self.api: API | None = None

    async def __aenter__(self) -> "XClient":
        cookie_header = "; ".join(
            f"{key}={value}" for key, value in self.cookies.items()
        )
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.api = API(str(self.db_path), proxy=self.proxy, raise_when_no_account=True)
        account = await self.api.pool.get_account("hoshino-x")
        parsed = parse_cookies(cookie_header)
        if account is None:
            await self.api.pool.add_account_cookies("hoshino-x", cookie_header)
        elif account.cookies != parsed:
            account.cookies = parsed
            account.active = True
            account.error_msg = None
            account.locks = {}
            await self.api.pool.save(account)
        return self

    async def __aexit__(self, *args: object) -> None:
        self.api = None

    async def resolve_user_id(self, username: str) -> int:
        api = self._require_api()
        try:
            user = await api.user_by_login(username)
        except SystemExit as exc:
            raise XUpstreamError("twscrape aborted user lookup") from exc
        except Exception as exc:
            await self._translate_error(exc, USER_LOOKUP_ENDPOINT)
            raise AssertionError("unreachable") from exc
        if user is None:
            raise XUserNotFound(f"X user @{username} was not found")
        return user.id

    async def fetch_recent(self, user_id: int, limit: int) -> list[Tweet]:
        api = self._require_api()
        try:
            tweets = await gather(api.user_tweets(int(user_id), limit=max(1, limit)))
        except SystemExit as exc:
            raise XUpstreamError("twscrape aborted tweet request") from exc
        except Exception as exc:
            await self._translate_error(exc, USER_TWEETS_ENDPOINT)
            raise AssertionError("unreachable") from exc
        tweets.sort(key=lambda tweet: int(tweet.id))
        return tweets[: max(1, limit)]

    async def _translate_error(self, exc: Exception, endpoint: str) -> None:
        if not isinstance(exc, NoAccountError):
            raise exc
        api = self._require_api()
        account = await api.pool.get_account("hoshino-x")
        if account is None or not account.active:
            message = (
                account.error_msg if account is not None else "credential unavailable"
            )
            raise XAuthenticationError(message or "X credential is inactive") from exc
        lock_until = account.locks.get(endpoint)
        retry_at = self._timestamp(lock_until) if lock_until else time.time() + 900
        raise XRateLimited(endpoint, retry_at) from exc

    def _require_api(self) -> API:
        if self.api is None:
            raise RuntimeError("XClient is not initialized")
        return self.api

    @staticmethod
    def _timestamp(value: datetime) -> float:
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.timestamp()


__all__ = [
    "USER_LOOKUP_ENDPOINT",
    "USER_TWEETS_ENDPOINT",
    "XAuthenticationError",
    "XClient",
    "XRateLimited",
    "XUpstreamError",
    "XUserNotFound",
]
