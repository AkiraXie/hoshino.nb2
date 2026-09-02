import os
import sys

# twscrape mutates the process-global Loguru logger on import; load it before
# Hoshino sinks so the opt-in X plugin cannot strip NoneBot handlers later.
import twscrape as _twscrape  # noqa: F401
from nonebot.log import default_format, logger

from hoshino.core.config import config

_HOSHINO_MATCHER_MODULE = "module=hoshino.core.service"


def _is_redundant_matcher_log(record: dict) -> bool:
    """Return whether NoneBot is duplicating Hoshino's matcher lifecycle log."""
    if record["name"].split(".", 1)[0] != "nonebot":
        return False

    message = record["message"]
    if _HOSHINO_MATCHER_MODULE not in message:
        return False

    return message.startswith("Event will be handled by ") or message.endswith(" running complete")


class Filter:
    """Apply the configured level and remove duplicate matcher lifecycle logs."""

    def __init__(self) -> None:
        self.level = "DEBUG"

    def __call__(self, record: dict):
        record["name"] = record["name"].split(".", 1)[0]
        levelno = logger.level(self.level).no
        return record["level"].no >= levelno and not _is_redundant_matcher_log(record)


_configured = False


def configure() -> None:
    """配置 loguru handlers。由 bootstrap() 调用。"""
    global _configured
    if _configured:
        return
    _configured = True

    log_root = "logs/"
    log_info_root = "logs/info/"
    log_error_root = "logs/error/"
    os.makedirs(log_root, exist_ok=True)
    logger.remove()
    hoshino_filter = Filter()
    hoshino_filter.level = "DEBUG" if config.debug else "INFO"
    logger.add(
        sys.stdout,
        colorize=True,
        diagnose=False,
        filter=hoshino_filter,
        format=default_format,
    )
    logger.add(
        log_info_root + "hsn{time:YYYYMMDD}.log",
        colorize=True,
        rotation="00:00",
        level="INFO",
        format=default_format,
        diagnose=False,
        retention="10 days",
    )
    logger.add(
        log_error_root + "hsn{time:YYYYMMDD}_error.log",
        colorize=True,
        rotation="00:00",
        level="ERROR",
        format=default_format,
        diagnose=False,
        retention="10 days",
    )
