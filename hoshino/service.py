"""Compatibility shim for hoshino.core.service."""

from hoshino.core.service import MatcherWrapper as MatcherWrapper
from hoshino.core.service import Service as Service
from hoshino.core.service import _loaded_matchers as _loaded_matchers
from hoshino.core.service import _loaded_services as _loaded_services
from hoshino.core.service import _matcher_sv_map as _matcher_sv_map

__all__ = [
    "MatcherWrapper",
    "Service",
    "_loaded_matchers",
    "_loaded_services",
    "_matcher_sv_map",
]
