"""权限系统 — 组合 OB11 predicates + NoneBot SUPERUSER"""

from __future__ import annotations

from hoshino.platform.ob11.permission import (
    GROUP as GROUP,
    GROUP_ADMIN as GROUP_ADMIN,
    GROUP_OWNER as GROUP_OWNER,
    PRIVATE as PRIVATE,
)
from nonebot.permission import SUPERUSER as SUPERUSER
from nonebot.permission import Permission as Permission
from nonebot.permission import USER as USER

ADMIN = SUPERUSER | GROUP_ADMIN | GROUP_OWNER
PADMIN = SUPERUSER | GROUP_ADMIN | GROUP_OWNER | PRIVATE
OWNER = SUPERUSER | GROUP_OWNER
POWNER = SUPERUSER | GROUP_OWNER | PRIVATE
NORMAL = SUPERUSER | GROUP | PRIVATE

__all__ = [
    "ADMIN",
    "GROUP",
    "GROUP_ADMIN",
    "GROUP_OWNER",
    "NORMAL",
    "OWNER",
    "PADMIN",
    "POWNER",
    "PRIVATE",
    "Permission",
    "SUPERUSER",
    "USER",
]
