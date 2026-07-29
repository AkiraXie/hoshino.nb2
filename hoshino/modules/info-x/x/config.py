"""Runtime settings for the X polling service."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class XSettings:
    proxy: str | None = None
    max_tweets_per_account: int = 10
    max_media_per_tweet: int = 10
    poll_tick_seconds: float = 20.0
    hot_interval_seconds: int = 180
    cold_interval_seconds: int = 1800
    cold_after_seconds: int = 86400
    request_timeout_seconds: float = 30.0
    rate_limit_requests: int = 20
    rate_limit_window_seconds: int = 900
    retry_base_seconds: float = 60.0
    retry_max_seconds: float = 1800.0
    delivery_retry_base_seconds: float = 5.0
    delivery_retry_max_seconds: float = 900.0
    delivery_max_attempts: int = 20

    @property
    def rate_interval(self) -> float:
        return max(
            1.0, self.rate_limit_window_seconds / max(1, self.rate_limit_requests)
        )


__all__ = ["XSettings"]
