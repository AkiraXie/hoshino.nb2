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
