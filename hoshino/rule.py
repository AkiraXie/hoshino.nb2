"""Compatibility shim for hoshino.core.rule."""

from hoshino.core.rule import fullmatch as fullmatch
from hoshino.core.rule import keyword as keyword
from hoshino.core.rule import regex as regex
from nonebot.rule import Rule as Rule

__all__ = ["Rule", "fullmatch", "keyword", "regex"]
