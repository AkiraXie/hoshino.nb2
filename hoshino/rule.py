'''
Author: AkiraXie
Date: 2021-01-28 14:10:09
LastEditors: AkiraXie
LastEditTime: 2021-02-04 03:01:55
Description: 
Github: http://github.com/AkiraXie/
'''
import re
from typing import Union
from nonebot.typing import T_State
from nonebot.adapters.cqhttp import Bot, Event
from nonebot.rule import ArgumentParser,Rule, to_me
from hoshino.util import normalize_str


def regex(regex: str, flags: Union[int, re.RegexFlag] = 0, normal: bool = True) -> Rule:
    """
    :说明:
      改自`nonebot.rule.regex`
      根据正则表达式进行匹配。
      可以通过 ``state["_matched"]`` 获取正则表达式匹配成功的文本。
      可以通过 ``state["match"]`` 获取正则表达式匹配成功后的 ``match``
    :参数:
      * ``regex: str``: 正则表达式
      * ``flags: Union[int, re.RegexFlag]``: 正则标志
    \:\:\:tip 提示
    正则表达式匹配使用 search 而非 match，如需从头匹配请使用 ``r"^xxx"`` 来确保匹配开头
    \:\:\:
    """

    pattern = re.compile(regex, flags)

    async def _regex(bot: Bot, event: Event, state: T_State) -> bool:
        if event.get_type() != "message":
            return False
        text = str(event.get_message())
        if normal:
            text = normalize_str(text)
        matched = pattern.search(text)
        if matched:
            state['match'] = matched
            state["_matched"] = matched.group()
            return True
        else:
            return False

    return Rule(_regex)


def keyword(*keywords: str, normal: bool = True) -> Rule:
    """
    改自 nonebot.rule.keyword
    :说明:

      匹配消息关键词

    :参数:

      * ``*keywords: str``: 关键词
    """

    async def _keyword(bot: "Bot", event: "Event", state: T_State) -> bool:
        if event.get_type() != "message":
            return False
        text = event.get_plaintext()
        if normal:
            text = normalize_str(text)
        return bool(text and any(keyword in text for keyword in keywords))

    return Rule(_keyword)
