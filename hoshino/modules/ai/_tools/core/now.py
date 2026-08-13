"""core/now：查询当前本地时间。纯函数，不接收 context。"""

from __future__ import annotations

from datetime import datetime


def now() -> str:
    """查询当前本地时间，返回 ISO8601 格式字符串。"""
    return datetime.now().isoformat(timespec="seconds")
