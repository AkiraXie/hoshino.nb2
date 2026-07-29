"""Shared dispatch utilities for content delivery pipelines."""

from __future__ import annotations

import random


def retry_delay(attempts: int, base: float = 30.0, maximum: float = 600.0) -> float:
    """Exponential backoff with jitter.

    Returns a delay in seconds: base * 2^attempts, capped at *maximum*,
    plus up to 20% random jitter (max 30s).
    """
    base = max(1.0, base)
    maximum = max(base, maximum)
    delay = min(maximum, base * (2 ** min(max(0, attempts), 10)))
    return delay + random.uniform(0, min(delay * 0.2, 30.0))
