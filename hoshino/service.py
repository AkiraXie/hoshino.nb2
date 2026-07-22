"""Compatibility shim for hoshino.core.service."""

from hoshino.core.service import Service as Service
from hoshino.core.service import _loaded_services as _loaded_services
from hoshino.core.matcher import MatcherWrapper as MatcherWrapper

__all__ = [
    "MatcherWrapper",
    "Service",
    "_loaded_services",
]
