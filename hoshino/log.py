from nonebot.log import logger, default_format
import os
import sys
from . import config
from .service import _loaded_matchers


class Filter:
    """
    改自 ``nonebot.log.Filter``
    """

    def __init__(self) -> None:
        self.level = "DEBUG"

    def __call__(self, record: dict):
        record["name"] = record["name"].split(".")[0]
        levelno = logger.level(self.level).no
        nologmatchers = map(str, _loaded_matchers.keys())
        nologflag = all(
            nologmatcher not in record["message"] for nologmatcher in nologmatchers
        )
        return record["level"].no >= levelno and nologflag


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
