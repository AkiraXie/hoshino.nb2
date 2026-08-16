"""Generic permission primitives — platform-independent"""

from __future__ import annotations

from nonebot.permission import SUPERUSER as SUPERUSER
from nonebot.permission import USER as USER
from nonebot.permission import Permission as Permission

__all__ = [
    "SUPERUSER",
    "USER",
    "Permission",
]
