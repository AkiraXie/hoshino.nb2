"""Compatibility shim for hoshino.core.config."""

from hoshino.core.config import HoshinoConfig as HoshinoConfig
from hoshino.core.config import config as config

__all__ = ["HoshinoConfig", "config"]
