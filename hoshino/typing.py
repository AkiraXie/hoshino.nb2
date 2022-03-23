"""
Author: AkiraXie
Date: 2021-01-28 14:24:11
LastEditors: AkiraXie
LastEditTime: 2022-02-16 22:11:31
Description: 
Github: http://github.com/AkiraXie/
"""
from typing import (
    List,
    Set,
    Any,
    Dict,
    TYPE_CHECKING,
    Union,
    TypeVar,
    Optional,
    Callable,
    Iterable,
    Final,
    Type,
    Awaitable,
    NoReturn,
)
from multidict import CIMultiDictProxy
from nonebot.typing import T_State, T_Handler
from nonebot.exception import (
    FinishedException,
    IgnoredException,
    PausedException,
    RejectedException,
)
from argparse import Namespace

if TYPE_CHECKING:
    from nonebot.adapters import Bot, Event
