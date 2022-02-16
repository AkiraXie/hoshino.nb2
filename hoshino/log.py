'''
Author: AkiraXie
Date: 2021-02-22 02:35:32
LastEditors: AkiraXie
LastEditTime: 2022-01-13 22:34:02
Description: 
Github: http://github.com/AkiraXie/
'''
from nonebot.log import logger,default_format
import os
import sys
from . import hsn_config
from .service import _loaded_matchers


class LoggerWrapper:
    def __init__(self, name: str) -> None:
        self.name = name

    def exception(self, message: str, exception=True):
        return logger.opt(colors=True, exception=exception).exception(
            f"<r><ly>{self.name}</> | {message}</>")

    def error(self, message: str, exception=True):
        return logger.opt(colors=True, exception=exception).error(
            f"<r><ly>{self.name}</> | {message}</>")

    def critical(self, message: str):
        return logger.opt(colors=True).critical(
            f"<ly>{self.name}</> | {message}")

    def warning(self, message: str):
        return logger.opt(colors=True).warning(
            f"<ly>{self.name}</> | {message}")

    def success(self, message: str):
        return logger.opt(colors=True).success(
            f"<ly>{self.name}</> | {message}")

    def info(self, message: str):
        return logger.opt(colors=True).info(
            f"<ly>{self.name}</> | {message}")

    def debug(self, message: str):
        return logger.opt(colors=True).debug(
            f"<ly>{self.name}</> | {message}")


class Filter:
    '''
    改自 ``nonebot.log.Filter``
    '''

    def __init__(self) -> None:
        self.level = "DEBUG"

    def __call__(self, record: dict):
        record["name"] = record["name"].split(".")[0]
        levelno = logger.level(self.level).no
        nologmatchers = map(str, _loaded_matchers.keys())
        nologflag = all(
            nologmatcher not in record['message'] for nologmatcher in nologmatchers)
        return record["level"].no >= levelno and nologflag


log_root = 'logs/'
log_info_root = 'logs/info/'
log_error_root = 'logs/error/'
os.makedirs(log_root, exist_ok=True)
logger.remove()
hoshino_filter = Filter()
hoshino_filter.level = 'DEBUG' if hsn_config.debug else "INFO"
logger.add(sys.stdout,
           colorize=True,
           diagnose=False,
           filter=hoshino_filter,
           format=default_format)
logger.add(log_info_root+'hsn{time:YYYYMMDD}.log',colorize=True, rotation='00:00', level='INFO',format = default_format,diagnose=False,retention="10 days")
logger.add(log_error_root+'hsn{time:YYYYMMDD}_error.log',colorize=True,
           rotation='00:00', level='ERROR',format = default_format,diagnose=False,retention="10 days")
