"""Runtime settings for the X polling service."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import nonebot

from .sv import sv


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

    @property
    def rate_interval(self) -> float:
        return max(
            1.0, self.rate_limit_window_seconds / max(1, self.rate_limit_requests)
        )


def _int(config: dict[str, Any], name: str, default: int) -> int:
    try:
        return int(config.get(name, default))
    except (TypeError, ValueError):
        return default


def _float(config: dict[str, Any], name: str, default: float) -> float:
    try:
        return float(config.get(name, default))
    except (TypeError, ValueError):
        return default


def get_x_settings() -> XSettings:
    config = sv.get_config()
    driver_config = nonebot.get_driver().config.model_dump()
    proxy = config.get("proxy") or driver_config.get("x_proxy")
    return XSettings(
        proxy=str(proxy) if proxy else None,
        max_tweets_per_account=_int(config, "max_tweets_per_account", 10),
        max_media_per_tweet=_int(config, "max_media_per_tweet", 10),
        poll_tick_seconds=_float(config, "poll_tick_seconds", 20.0),
        hot_interval_seconds=_int(config, "hot_interval_seconds", 180),
        cold_interval_seconds=_int(config, "cold_interval_seconds", 1800),
        cold_after_seconds=_int(config, "cold_after_seconds", 86400),
        request_timeout_seconds=_float(config, "request_timeout_seconds", 30.0),
        rate_limit_requests=_int(config, "rate_limit_requests", 20),
        rate_limit_window_seconds=_int(config, "rate_limit_window_seconds", 900),
        retry_base_seconds=_float(config, "retry_base_seconds", 60.0),
        retry_max_seconds=_float(config, "retry_max_seconds", 1800.0),
        delivery_retry_base_seconds=_float(config, "delivery_retry_base_seconds", 5.0),
        delivery_retry_max_seconds=_float(config, "delivery_retry_max_seconds", 900.0),
    )


__all__ = ["XSettings", "get_x_settings"]
