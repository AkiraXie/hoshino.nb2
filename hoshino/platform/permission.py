"""Adapter-aware permissions backed by nonebot-plugin-uninfo."""

from nonebot.permission import SUPERUSER, Permission
from nonebot_plugin_uninfo import (
    ADMIN as uninfo_admin,  # noqa: N811  # 别名刻意避让本模块 ADMIN/OWNER 权限常量
)
from nonebot_plugin_uninfo import (
    GROUP as GROUP,
)
from nonebot_plugin_uninfo import (
    OWNER as uninfo_owner,  # noqa: N811  # 别名刻意避让本模块 ADMIN/OWNER 权限常量
)
from nonebot_plugin_uninfo import (
    PRIVATE as PRIVATE,
)

GROUP_ADMIN: Permission = uninfo_admin()
GROUP_OWNER: Permission = uninfo_owner()

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
]
