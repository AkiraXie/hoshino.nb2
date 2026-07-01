"""Compatibility shim for hoshino.core.log."""

from hoshino.core.log import Filter as Filter
from hoshino.core.log import configure as configure
from nonebot.log import logger as logger

__all__ = ["Filter", "configure", "logger"]
