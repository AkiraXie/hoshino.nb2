'''
Author: AkiraXie
Date: 2021-01-28 14:24:11
LastEditors: AkiraXie
LastEditTime: 2021-02-09 23:54:29
Description: 
Github: http://github.com/AkiraXie/
'''
from typing import List, Set, Any, Dict, Union, TypeVar, Optional, Callable, Iterable, Final, Type,Awaitable
from multidict import CIMultiDictProxy
from nonebot.typing import T_State,T_Handler,T_ArgsParser
from nonebot.exception import FinishedException, IgnoredException,PausedException,RejectedException
from argparse import Namespace
