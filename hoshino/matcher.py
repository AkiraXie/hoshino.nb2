"""
Author: AkiraXie
Date: 2021-01-28 14:34:06
LastEditors: AkiraXie
LastEditTime: 2021-06-09 02:30:37
Description: 
Github: http://github.com/AkiraXie/
"""
from nonebot.matcher import Matcher, matchers
from nonebot.plugin import (
    on_command,
    on_message,
    on_startswith,
    on_endswith,
    on_notice,
    on_keyword,
    on_metaevent,
    on_request,
    on_shell_command,
)


def get_matchers() -> list:
    return matchers.items()
