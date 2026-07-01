"""Compatibility shim for hoshino.core.permission."""

from hoshino.core.permission import (
    ADMIN as ADMIN,
    GROUP as GROUP,
    GROUP_ADMIN as GROUP_ADMIN,
    GROUP_OWNER as GROUP_OWNER,
    NORMAL as NORMAL,
    OWNER as OWNER,
    PADMIN as PADMIN,
    POWNER as POWNER,
    PRIVATE as PRIVATE,
    Permission as Permission,
    SUPERUSER as SUPERUSER,
    USER as USER,
)

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
