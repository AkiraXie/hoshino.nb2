'''
Author: AkiraXie
Date: 2021-01-28 14:10:09
LastEditors: AkiraXie
LastEditTime: 2021-01-28 14:14:04
Description: 
Github: http://github.com/AkiraXie/
'''
from typing import Union
import re
from nonebot.typing import T_State
from nonebot.adapters import Bot, Event
from nonebot.rule import Rule, to_me

def regex(regex: str, flags: Union[int, re.RegexFlag] = 0) -> Rule:
    """
    :说明:
      改自`nonebot.rule.regex`
      根据正则表达式进行匹配。
      可以通过 ``state["_matched"]`` 获取正则表达式匹配成功的文本。
      可以通过 ``state["match"]`` 获取正则表达式匹配成功后的`match`
      可以通过
      
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
        matched = pattern.search(str(event.get_message()))
        if matched:
            state['match']=matched
            state["_matched"] = matched.group()
            return True
        else:
            state['match']=None
            state["_matched"] = None
            return False

    return Rule(_regex)