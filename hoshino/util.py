'''
Author: AkiraXie
Date: 2021-01-28 14:29:01
LastEditors: AkiraXie
LastEditTime: 2021-01-29 02:08:32
Description: 
Github: http://github.com/AkiraXie/
'''
from typing import ItemsView, Iterable, Optional
import nonebot
from nonebot.adapters.cqhttp import Bot
from nonebot.matcher import Matcher
from nonebot.permission import SUPERUSER
from nonebot.plugin import on_command
from nonebot.rule import Rule


def get_bot_list() -> ItemsView[str, Bot]:
    return nonebot.get_bots().items()


def sucmd(name: str,rule:Rule=Rule(),aliases: Optional[Iterable] = None, **kwargs) -> Matcher:
    kwargs['aliases'] = aliases
    kwargs['permission'] = SUPERUSER
    return on_command(name, **kwargs)