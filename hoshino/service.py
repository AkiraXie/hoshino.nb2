"""
Author: AkiraXie
Date: 2021-01-28 00:44:32
LastEditors: AkiraXie
LastEditTime: 2022-02-16 23:03:43
Description: 
Github: http://github.com/AkiraXie/
"""
import asyncio
import re
import os
import json
from collections import defaultdict
import nonebot
from nonebot.params import Depends
from nonebot.matcher import current_bot, current_event
from nonebot.message import run_preprocessor
from hoshino import Bot, service_dir as _service_dir, Message, MessageSegment, Matcher
from hoshino.message import MessageTemplate
from hoshino.event import Event
from hoshino.matcher import (
    on_message,
    on_startswith,
    on_endswith,
    on_notice,
    on_request,
)
from hoshino.permission import ADMIN, NORMAL, OWNER, Permission, SUPERUSER
from hoshino.util import _strip_cmd
from hoshino.rule import (
    ArgumentParser,
    Rule,
    fullmatch,
    to_me,
    regex,
    keyword,
    command,
    shell_command,
)
from hoshino.typing import (
    T_Handler,
    Dict,
    Iterable,
    Optional,
    Union,
    T_State,
    List,
    Type,
    FinishedException,
    PausedException,
    RejectedException,
)

_illegal_char = re.compile(r'[\\/:*?"<>|\.!！]')
_loaded_services: Dict[str, "Service"] = {}
_loaded_matchers: Dict["Type[Matcher]", "MatcherWrapper"] = {}
from hoshino.log import LoggerWrapper


def _iter_to_set(words: Iterable) -> set:
    if isinstance(words, str):
        res = set([words])
    elif not isinstance(words, set):
        if words:
            res = (
                set([words])
                if len(words) == 1 and isinstance(words, tuple)
                else set(words)
            )
        else:
            res = set()
    else:
        res = words
    return res


def _save_service_data(service: "Service"):
    data_file = os.path.join(_service_dir, f"{service.name}.json")
    with open(data_file, "w", encoding="utf8") as f:
        json.dump(
            {
                "name": service.name,
                "enable_group": list(service.enable_group),
                "disable_group": list(service.disable_group),
            },
            f,
            ensure_ascii=False,
            indent=2,
        )


def _load_service_data(service_name: str) -> dict:
    data_file = os.path.join(_service_dir, f"{service_name}.json")
    if not os.path.exists(data_file):
        return {}
    with open(data_file, encoding="utf8") as f:
        data = json.load(f)
        return data


class Service:
    def __init__(
        self,
        name: str,
        manage_perm: Permission = ADMIN,
        enable_on_default: bool = True,
        visible: bool = True,
    ):
        """
        Descrption:  定义一个服务

        Params:

        *`name` : 服务名字

        *`manage_perm` : 管理服务的权限,是一`Permission`实例,`ADMIN`和`OWNER`和`SUPERSUSER`是允许的

        *`enable_on_default` : 默认开启状态

        *`visible` : 默认可见状态
        """
        assert (
            not _illegal_char.search(name) or not name.isdigit()
        ), 'Service name cannot contain character in [\\/:*?"<>|.] or be pure number'
        assert manage_perm in (
            ADMIN,
            OWNER,
            SUPERUSER,
        ), "Service manage_perm is illegal"
        self.name = name
        self.manage_perm = manage_perm
        self.enable_on_default = enable_on_default
        self.visible = visible
        assert (
            self.name not in _loaded_services
        ), f'Service name "{self.name}" already exist!'
        _loaded_services[self.name] = self
        data = _load_service_data(self.name)
        self.enable_group = set(data.get("enable_group", []))
        self.disable_group = set(data.get("disable_group", []))
        self.logger = LoggerWrapper(self.name)
        self.matchers = []

    @staticmethod
    def get_loaded_services() -> Dict[str, "Service"]:
        return _loaded_services

    def set_enable(self, group_id):
        self.enable_group.add(group_id)
        self.disable_group.discard(group_id)
        _save_service_data(self)

    def set_disable(self, group_id):
        self.enable_group.discard(group_id)
        self.disable_group.add(group_id)
        _save_service_data(self)

    async def get_enable_groups(self) -> Dict[int, List[Bot]]:
        gl = defaultdict(list)
        for bot in nonebot.get_bots().values():
            sgl = set(g["group_id"] for g in await bot.get_group_list())
            if self.enable_on_default:
                sgl = sgl - self.disable_group
            else:
                sgl = sgl & self.enable_group
            for g in sgl:
                gl[g].append(bot)
        return gl

    @property
    def config(self) -> dict:
        filename = f"hoshino/service_config/{self.name}.json"
        try:
            with open(filename, encoding="utf8") as f:
                return json.load(f)
        except:
            self.logger.error(f"Failed to load config")
            return dict()

    def check_enabled(self, group_id: int) -> bool:
        return bool(
            (group_id in self.enable_group)
            or (self.enable_on_default and group_id not in self.disable_group)
        )

    def check_service(self, only_to_me: bool = False, only_group: bool = True) -> Rule:
        async def _cs(bot: Bot, event: Event, state: T_State) -> bool:
            if not "group_id" in event.__dict__:
                return not only_group
            else:
                group_id = event.group_id
                return self.check_enabled(group_id)

        rule = Rule(_cs)
        if only_to_me:
            rule = rule & (to_me())
        return rule

    @staticmethod
    def add_nonebot_plugin(
        plugin_name:str,        
        manage_perm: Permission = ADMIN,
        enable_on_default: bool = True,
        visible: bool = True) -> "Service":
        plugin = nonebot.load_plugin(plugin_name)
        sv = Service(plugin_name.replace("nonebot_plugin_",""),manage_perm,enable_on_default,visible)
        if matchers := plugin.matcher :
            for matcher in matchers:
               sv.add_nonebot_plugin_matcher(matcher)    
        return sv

    def add_nonebot_plugin_matcher(self,matcher: Type[Matcher], permission: Permission = NORMAL) -> "MatcherWrapper":
        rule =  self.check_service(False,False)
        matcher.rule = matcher.rule & rule
        matcher.permission = permission
        mw = MatcherWrapper(
            self,
            f"{matcher.type}.from_nonebot_plugin",
            matcher.priority,
            matcher,
        )
        self.matchers.append(str(mw))
        _loaded_matchers[mw.matcher] = mw
        return mw
    
    def on_command(
        self,
        name: str,
        only_to_me: bool = False,
        aliases: Optional[Iterable] = None,
        only_group: bool = True,
        permission: Permission = NORMAL,
        **kwargs,
    ) -> "MatcherWrapper":
        kwargs["permission"] = permission
        rule = self.check_service(only_to_me, only_group)
        kwargs["rule"] = rule & kwargs.pop("rule", Rule())
        priority = kwargs.get("priority", 1)
        handlers = kwargs.pop("handlers", [])
        handlers.insert(0, _strip_cmd)
        kwargs["handlers"] = handlers
        commands = set([name]) | (_iter_to_set(aliases) or set())
        kwargs["rule"] = kwargs["rule"] & command(*commands)
        mw = MatcherWrapper(
            self,
            "Message.command",
            priority,
            on_message(  _depth=1, **kwargs),
            command=name,
            only_group=only_group,
        )
        self.matchers.append(str(mw))
        _loaded_matchers[mw.matcher] = mw
        return mw

    def on_shell_command(
        self,
        name: str,
        only_to_me: bool = False,
        aliases: Optional[Iterable] = None,
        parser: Optional[ArgumentParser] = None,
        only_group: bool = True,
        permission: Permission = NORMAL,
        **kwargs,
    ) -> "MatcherWrapper":
        kwargs["permission"] = permission
        rule = self.check_service(only_to_me, only_group)
        kwargs["rule"] = rule & kwargs.pop("rule", Rule())
        priority = kwargs.get("priority", 1)
        handlers = kwargs.pop("handlers", [])
        handlers.insert(0, _strip_cmd)
        kwargs["handlers"] = handlers
        commands = set([name]) | (_iter_to_set(aliases) or set())
        kwargs["rule"] = kwargs["rule"] & shell_command(*commands, parser=parser)
        mw = MatcherWrapper(
            self,
            "Message.shell_command",
            priority,
            on_message(  _depth=1, **kwargs),
            command=name,
            only_group=only_group,
        )
        self.matchers.append(str(mw))
        _loaded_matchers[mw.matcher] = mw
        return mw

    def on_startswith(
        self,
        msg: str,
        only_to_me: bool = False,
        only_group: bool = True,
        permission: Permission = NORMAL,
        **kwargs,
    ) -> "MatcherWrapper":
        kwargs["permission"] = permission
        rule = self.check_service(only_to_me, only_group)
        kwargs["rule"] = rule & kwargs.pop("rule", Rule())
        priority = kwargs.get("priority", 1)
        mw = MatcherWrapper(
            self,
            "Message.startswith",
            priority,
            on_startswith(msg,   _depth=1, **kwargs),
            startswith=msg,
            only_group=only_group,
        )
        self.matchers.append(str(mw))
        _loaded_matchers[mw.matcher] = mw
        return mw

    def on_endswith(
        self,
        msg: str,
        only_to_me: bool = False,
        only_group: bool = True,
        permission: Permission = NORMAL,
        **kwargs,
    ) -> "MatcherWrapper":
        kwargs["permission"] = permission
        rule = self.check_service(only_to_me, only_group)
        kwargs["rule"] = rule & kwargs.pop("rule", Rule())
        priority = kwargs.get("priority", 1)
        mw = MatcherWrapper(
            self,
            "Message.endswith",
            priority,
            on_endswith(msg,   _depth=1, **kwargs),
            endswith=msg,
            only_group=only_group,
        )
        self.matchers.append(str(mw))
        _loaded_matchers[mw.matcher] = mw
        return mw

    def on_keyword(
        self,
        keywords: Iterable,
        normal: bool = True,
        only_to_me: bool = False,
        only_group: bool = True,
        permission: Permission = NORMAL,
        **kwargs,
    ) -> "MatcherWrapper":
        keywords = _iter_to_set(keywords)
        kwargs["permission"] = permission
        rule = self.check_service(only_to_me, only_group)
        kwargs["rule"] = (
            keyword(*keywords, normal=normal) & rule & kwargs.pop("rule", Rule())
        )
        priority = kwargs.get("priority", 1)
        mw = MatcherWrapper(
            self,
            "Message.keyword",
            priority,
            on_message(  _depth=1, **kwargs),
            keywords=str(keywords),
            only_group=only_group,
        )
        self.matchers.append(str(mw))
        _loaded_matchers[mw.matcher] = mw
        return mw

    def on_fullmatch(
        self,
        keywords: Iterable,
        normal: bool = True,
        only_to_me: bool = False,
        only_group: bool = True,
        permission: Permission = NORMAL,
        **kwargs,
    ) -> "MatcherWrapper":
        keywords = _iter_to_set(keywords)
        kwargs["permission"] = permission
        rule = self.check_service(only_to_me, only_group)
        kwargs["rule"] = (
            fullmatch(*keywords, normal=normal) & rule & kwargs.pop("rule", Rule())
        )
        priority = kwargs.get("priority", 1)
        mw = MatcherWrapper(
            self,
            "Message.fullmatch",
            priority,
            on_message(  _depth=1, **kwargs),
            keywords=str(keywords),
            only_group=only_group,
        )
        self.matchers.append(str(mw))
        _loaded_matchers[mw.matcher] = mw
        return mw

    def on_regex(
        self,
        pattern: str,
        flags: Union[int, re.RegexFlag] = 0,
        normal: bool = True,
        full_match: bool = True,
        only_to_me: bool = False,
        only_group: bool = True,
        permission: Permission = NORMAL,
        **kwargs,
    ) -> "MatcherWrapper":
        """
        根据正则表达式进行匹配。
        可以通过 ``state["_matched"]`` 获取正则表达式匹配成功的文本。
        可以通过 ``state["match"]`` 获取正则表达式匹配成功后的`match`
        """
        rule = self.check_service(only_to_me, only_group)
        rule = (
            regex(pattern, flags, normal, full_match)
            & rule
            & kwargs.pop("rule", Rule())
        )
        priority = kwargs.get("priority", 1)
        mw = MatcherWrapper(
            self,
            "Message.regex",
            priority,
            on_message(rule, permission,   _depth=1, **kwargs),
            pattern=str(pattern),
            flags=str(flags),
            only_group=only_group,
        )
        self.matchers.append(str(mw))
        _loaded_matchers[mw.matcher] = mw
        return mw

    def on_message(
        self,
        only_to_me: bool = False,
        only_group: bool = True,
        permission: Permission = NORMAL,
        log:bool = False,
        **kwargs,
    ) -> "MatcherWrapper":
        kwargs["permission"] = permission
        rule = self.check_service(only_to_me, only_group)
        kwargs["rule"] = rule & kwargs.pop("rule", Rule())
        priority = kwargs.get("priority", 1)
        mw = MatcherWrapper(
            self,
            "Message.message",
            priority,
            on_message(  _depth=1, **kwargs),
            log,
            only_group=only_group,
        )
        self.matchers.append(str(mw))
        _loaded_matchers[mw.matcher] = mw
        return mw

    def on_notice(self, only_group: bool = True, **kwargs) -> "MatcherWrapper":
        rule = self.check_service(0, only_group) & kwargs.pop("rule", Rule())
        priority = kwargs.get("priority", 1)
        mw = MatcherWrapper(
            self,
            "Notice",
            priority,
            on_notice(rule,   _depth=1, **kwargs),
            only_group=only_group,
        )
        self.matchers.append(str(mw))
        _loaded_matchers[mw.matcher] = mw
        return mw

    def on_request(self, only_group: bool = True, **kwargs) -> "MatcherWrapper":
        rule = self.check_service(0, only_group) & kwargs.pop("rule", Rule())
        priority = kwargs.get("priority", 1)
        mw = MatcherWrapper(
            self,
            "Request",
            priority,
            on_request(rule,   _depth=1, **kwargs),
            only_group=only_group,
        )
        self.matchers.append(str(mw))
        _loaded_matchers[mw.matcher] = mw
        return mw

    async def broadcast(self, msgs: Optional[Iterable], tag="", interval_time=0.5):
        if isinstance(msgs, (str, Message, MessageSegment)):
            msgs = (msgs,)
        gdict = await self.get_enable_groups()
        for gid in gdict.keys():
            for bot in gdict[gid]:
                sid = int(bot.self_id)
                for msg in msgs:
                    await asyncio.sleep(interval_time)
                    try:
                        await bot.send_group_msg(self_id=sid, group_id=gid, message=msg)
                        self.logger.info(f"{sid}在群{gid}投递{tag}成功")
                    except:
                        self.logger.error(f"{sid}在群{gid}投递{tag}失败")


class MatcherWrapper:
    """
    封装了 ``nonebot.matcher.Matcher`` ,使之可以受Service干预。

    并将 ``Matcher`` 常见的类方法进行了封装，如果需要其他类方法，请调用 ``.matcher.* ``
    """

    def __init__(
        self, sv: Service, type: str, priority: int, matcher: Type[Matcher],log:bool=True, **info
    ) -> None:
        self.matcher = matcher
        self.sv = sv
        self.priority = priority
        self.info = info
        self.type = type
        self.log = log

    @staticmethod
    def get_loaded_matchers() -> List[str]:
        return list(map(str, _loaded_matchers.values()))

    def handle(self, parameterless: Optional[list] = None):
        def deco(func: T_Handler):
            return self.matcher.handle(parameterless)(func)

        return deco

    def __call__(self, func: T_Handler) -> T_Handler:
        return self.handle()(func)

    def receive(self, parameterless: Optional[list] = None):
        def deco(func: T_Handler):
            return self.matcher.receive(parameterless)(func)

        return deco

    def got(
        self,
        key: str,
        prompt: Optional[Union[str, Message, MessageSegment, MessageTemplate]] = None,
        args_parser: Optional[T_Handler] = None,
        parameterless: Optional[list] = None,
    ):
        def deco(func: T_Handler):
            return self.matcher.got(key, prompt, args_parser, parameterless)(func)

        return deco

    async def reject(
        self,
        prompt: Optional[Union[str, "Message", "MessageSegment"]] = None,
        *,
        call_header: bool = False,
        at_sender: bool = False,
        **kwargs,
    ):
        if prompt:
            await self.matcher.send(
                prompt, call_header=call_header, at_sender=at_sender, **kwargs
            )
        raise RejectedException

    async def pause(
        self,
        prompt: Optional[Union[str, "Message", "MessageSegment"]] = None,
        *,
        call_header: bool = False,
        at_sender: bool = False,
        **kwargs,
    ):
        if prompt:
            await self.send(
                prompt, call_header=call_header, at_sender=at_sender, **kwargs
            )
        raise PausedException

    async def send(
        self,
        message: Union[str, "Message", "MessageSegment"],
        *,
        call_header: bool = False,
        at_sender: bool = False,
        **kwargs,
    ):
        bot: Bot = current_bot.get()
        event: Event = current_event.get()
        return await bot.send(
            event, message, at_sender=at_sender, call_header=call_header, **kwargs
        )

    async def finish(
        self,
        message: Optional[Union[str, "Message", "MessageSegment"]] = None,
        *,
        call_header: bool = False,
        at_sender: bool = False,
        **kwargs,
    ):
        if message:
            await self.send(
                message, call_header=call_header, at_sender=at_sender, **kwargs
            )
        raise FinishedException

    def __str__(self) -> str:
        finfo = [
            f"{k}={v}".replace("<", "\<").replace(">", "\>")
            for k, v in self.info.items()
        ]
        return (
            f"<Matcher from Service {self.sv.name}, priority={self.priority}, type={self.type}, "
            + ", ".join(finfo)
            + ">"
        )

    def __repr__(self) -> str:
        return self.__str__()


async def log_matcherwrapper(matcher: Matcher):
    mw = _loaded_matchers.get(matcher.__class__, None)
    if mw and mw.log:
        mw.sv.logger.info(f"Event will be handled by <lc>{mw}</>")
        yield 
        mw.sv.logger.info(f"Event was completed handling by <lc>{mw}</>")
    else:
        yield

@run_preprocessor
async def _(_ = Depends(log_matcherwrapper,use_cache = False)):
    ...
