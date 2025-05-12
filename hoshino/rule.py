import re
from typing import Union, Set
from nonebot.rule import command, shell_command
from nonebot.typing import T_State
from nonebot.adapters.onebot.v11 import Bot, Event
from nonebot.rule import ArgumentParser, Rule, to_me
from hoshino.util import normalize_str


def regex(
    regex: str,
    flags: Union[int, re.RegexFlag] = 0,
    normal: bool = True,
    full_match: bool = True,
) -> Rule:
    """
    :说明:
      改自`nonebot.rule.regex`
      根据正则表达式进行匹配。
      可以通过 ``state["_matched"]`` 获取正则表达式匹配成功的文本。
      可以通过 ``state["match"]`` 获取正则表达式匹配成功后的 ``match``
    :参数:
      * ``regex: str``: 正则表达式
      * ``flags: Union[int, re.RegexFlag]``: 正则标志
      * ``normal: bool``: 是否规范字符串
      * ``full_match: bool``: 是否全批评字符串
    """

    pattern = re.compile(regex, flags)

    async def _regex(bot: Bot, event: Event, state: T_State) -> bool:
        if event.get_type() != "message":
            return False
        text = event.get_plaintext()
        if normal:
            text = normalize_str(text)
        matched = pattern.search(text) if not full_match else pattern.fullmatch(text)
        if matched:
            state["match"] = matched
            state["_matched"] = matched.group()
            state["_matched_groups"] = matched.groups()
            state["_matched_dict"] = matched.groupdict()
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

    async def _keyword(bot: Bot, event: Event, state: T_State) -> bool:
        if event.get_type() != "message":
            return False
        text = event.get_plaintext()
        if normal:
            text = normalize_str(text)
        return bool(text and any(kw in text for kw in keywords))

    return Rule(_keyword)


def fullmatch(*keywords: str, normal: bool = True) -> Rule:
    async def _fullmatch(bot: Bot, event: Event, state: T_State) -> bool:
        if event.get_type() != "message":
            return False
        text = event.get_plaintext()
        if normal:
            text = normalize_str(text)
        return bool(text and any(kw == text for kw in keywords))

    return Rule(_fullmatch)
