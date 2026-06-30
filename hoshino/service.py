import asyncio
import re
import os
import json
from collections import defaultdict
from typing import Iterable
import nonebot
from nonebot.params import Depends
from hoshino.hooks import run_preprocessor
from nonebot.exception import RejectedException, PausedException, FinishedException
from nonebot.rule import ArgumentParser, to_me, command, shell_command
from nonebot.adapters import Bot
from nonebot.adapters import Event
from nonebot.matcher import Matcher, current_bot, current_event
from hoshino.types import OneBotV11Message, OneBotV11MessageSegment
from hoshino import service_dir as _service_dir
from hoshino.message import MessageTemplate
from nonebot.plugin import (
    on_message,
    on_startswith,
    on_endswith,
    on_notice,
    on_request,
)
from hoshino.permission import ADMIN, NORMAL, OWNER, Permission, SUPERUSER
from hoshino.util import _strip_cmd
from hoshino.rule import (
    Rule,
    fullmatch,
    regex,
    keyword,
)
from hoshino.platform import (
    Target,
    event_scope_key,
    get_group_id,
    get_group_list,
    group_scope_key,
    platform_key,
    send_to_event,
    send_to_target,
)
from nonebot.typing import (
    T_Handler,
)
from nonebot_plugin_alconna import Alconna, on_alconna
from hoshino.logger_wrapper import LoggerWrapper


_illegal_char = re.compile(r'[\\/:*?"<>|\.!！]')
_loaded_services: dict[str, "Service"] = {}
_loaded_matchers: dict["type[Matcher]", "MatcherWrapper"] = {}


def _iter_to_set(words: set | list | tuple | str | None) -> set:
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
                "enable_scope": list(service.enable_scope),
                "disable_scope": list(service.disable_scope),
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
        assert not _illegal_char.search(name) or not name.isdigit(), (
            'Service name cannot contain character in [\\/:*?"<>|.] or be pure number'
        )
        assert manage_perm in (
            ADMIN,
            OWNER,
            SUPERUSER,
        ), "Service manage_perm is illegal"
        self.name = name
        self.manage_perm = manage_perm
        self.enable_on_default = enable_on_default
        self.visible = visible
        assert self.name not in _loaded_services, (
            f'Service name "{self.name}" already exist!'
        )
        _loaded_services[self.name] = self
        data = _load_service_data(self.name)
        self.enable_group = set(data.get("enable_group", []))
        self.disable_group = set(data.get("disable_group", []))
        self.enable_scope = set(data.get("enable_scope", []))
        self.disable_scope = set(data.get("disable_scope", []))
        self._migrate_legacy_scopes()
        self.logger = LoggerWrapper(self.name)
        self.matchers = []

    @staticmethod
    def get_loaded_services() -> dict[str, "Service"]:
        return _loaded_services

    def _migrate_legacy_scopes(self):
        self.enable_scope.update(group_scope_key(gid) for gid in self.enable_group)
        self.disable_scope.update(group_scope_key(gid) for gid in self.disable_group)

    def set_enable(self, group_id):
        self.enable_group.add(group_id)
        self.disable_group.discard(group_id)
        self.set_scope_enable(group_scope_key(group_id), save=False)
        _save_service_data(self)

    def set_disable(self, group_id):
        self.enable_group.discard(group_id)
        self.disable_group.add(group_id)
        self.set_scope_disable(group_scope_key(group_id), save=False)
        _save_service_data(self)

    def set_scope_enable(self, scope_key: str, *, save: bool = True):
        self.enable_scope.add(scope_key)
        self.disable_scope.discard(scope_key)
        if save:
            _save_service_data(self)

    def set_scope_disable(self, scope_key: str, *, save: bool = True):
        self.enable_scope.discard(scope_key)
        self.disable_scope.add(scope_key)
        if save:
            _save_service_data(self)

    async def get_enable_groups(self) -> dict[int, list[Bot]]:
        gl = defaultdict(list)
        for bot in nonebot.get_bots().values():
            platform = platform_key(bot)
            sgl = set(g["group_id"] for g in await get_group_list(bot))
            if self.enable_on_default:
                sgl = {
                    gid
                    for gid in sgl
                    if gid not in self.disable_group
                    and group_scope_key(gid, platform=platform) not in self.disable_scope
                }
            else:
                sgl = {
                    gid
                    for gid in sgl
                    if gid in self.enable_group
                    or group_scope_key(gid, platform=platform) in self.enable_scope
                }
            for g in sgl:
                gl[g].append(bot)
        return gl

    @property
    def config(self) -> dict:
        filename = f"hoshino/service_config/{self.name}.json"
        try:
            with open(filename, encoding="utf8") as f:
                return json.load(f)
        except (Exception, FileNotFoundError):
            self.logger.error("Failed to load config")
            return dict()

    def check_enabled(self, group_id: int) -> bool:
        return self.check_scope_enabled(group_scope_key(group_id), group_id)

    def check_scope_enabled(self, scope_key: str | None, group_id: int | None = None) -> bool:
        if scope_key:
            if scope_key in self.enable_scope:
                return True
            if scope_key in self.disable_scope:
                return False
        if group_id is not None:
            if group_id in self.enable_group:
                return True
            if group_id in self.disable_group:
                return False
        return bool(self.enable_on_default)

    def check_service(self, only_to_me: bool = False, only_group: bool = True) -> Rule:
        async def _cs(bot: Bot, event: Event) -> bool:
            group_id = get_group_id(event)
            if group_id is None:
                return not only_group
            return self.check_scope_enabled(event_scope_key(bot, event), int(group_id))

        rule = Rule(_cs)
        if only_to_me:
            rule = rule & (to_me())
        return rule

    @staticmethod
    def add_nonebot_plugin(
        plugin_name: str,
        manage_perm: Permission = ADMIN,
        enable_on_default: bool = True,
        visible: bool = True,
    ) -> "Service | None":
        names = nonebot.get_available_plugin_names()
        if plugin_name in names:
            return None
        plugin = nonebot.load_plugin(plugin_name)
        if not plugin:
            return None
        svname = plugin_name.replace("nonebot_plugin_", "").replace(
            "nonebot-plugin-", ""
        )
        sv = Service(svname, manage_perm, enable_on_default, visible)
        if matchers := plugin.matcher:
            for m in matchers:
                sv.add_nonebot_plugin_matcher(m)
        return sv

    def add_nonebot_plugin_matcher(self, matcher: type[Matcher]) -> "MatcherWrapper":
        rule = self.check_service(False, False)
        matcher.rule = matcher.rule & rule
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
        aliases: set | list | tuple | str | None = None,
        only_group: bool = True,
        permission: Permission = NORMAL,
        force_whitespace: bool | None = None,
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
        kwargs["rule"] = kwargs["rule"] & command(
            *commands, force_whitespace=force_whitespace
        )
        mw = MatcherWrapper(
            self,
            "Message.command",
            priority,
            on_message(**kwargs),
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
        aliases: set | list | tuple | str | None = None,
        parser: ArgumentParser | None = None,
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
            on_message(**kwargs),
            command=name,
            only_group=only_group,
        )
        self.matchers.append(str(mw))
        _loaded_matchers[mw.matcher] = mw
        return mw

    def on_alconna(
        self,
        command: Alconna | str,
        *,
        only_to_me: bool = False,
        only_group: bool = True,
        permission: Permission = NORMAL,
        aliases: set[str] | tuple[str, ...] | None = None,
        **kwargs,
    ) -> "MatcherWrapper":
        kwargs["permission"] = permission
        rule = self.check_service(only_to_me, only_group)
        kwargs["rule"] = rule & kwargs.pop("rule", Rule())
        priority = kwargs.get("priority", 1)
        matcher: Matcher = on_alconna(command, aliases=aliases, **kwargs)
        mw = MatcherWrapper(
            self,
            "Message.alconna",
            priority,
            matcher,
            command=str(command),
            only_group=only_group,
        )
        self.matchers.append(str(mw))
        _loaded_matchers[matcher.__class__] = mw
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
            on_startswith(msg, **kwargs),
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
            on_endswith(msg, **kwargs),
            endswith=msg,
            only_group=only_group,
        )
        self.matchers.append(str(mw))
        _loaded_matchers[mw.matcher] = mw
        return mw

    def on_keyword(
        self,
        keywords: set | list | tuple | str | None,
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
            on_message(**kwargs),
            keywords=str(keywords),
            only_group=only_group,
        )
        self.matchers.append(str(mw))
        _loaded_matchers[mw.matcher] = mw
        return mw

    def on_fullmatch(
        self,
        keywords: set | list | tuple | str | None,
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
            on_message(**kwargs),
            keywords=str(keywords),
            only_group=only_group,
        )
        self.matchers.append(str(mw))
        _loaded_matchers[mw.matcher] = mw
        return mw

    def on_regex(
        self,
        pattern: str,
        flags: int | re.RegexFlag = 0,
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
            on_message(rule, permission, **kwargs),
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
        log: bool = False,
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
            on_message(**kwargs),
            log,
            only_group=only_group,
        )
        self.matchers.append(str(mw))
        _loaded_matchers[mw.matcher] = mw
        return mw

    def on_notice(
        self, rule: Rule = Rule(), only_group: bool = True, permission=NORMAL, **kwargs
    ) -> "MatcherWrapper":
        rule = self.check_service(False, only_group) & rule
        priority = kwargs.get("priority", 1)
        mw = MatcherWrapper(
            self,
            "Notice",
            priority,
            on_notice(rule=rule, permission=permission, **kwargs),
            only_group=only_group,
        )
        self.matchers.append(str(mw))
        _loaded_matchers[mw.matcher] = mw
        return mw

    def on_request(self, only_group: bool = True, **kwargs) -> "MatcherWrapper":
        rule = self.check_service(False, only_group) & kwargs.pop("rule", Rule())
        priority = kwargs.get("priority", 1)
        mw = MatcherWrapper(
            self,
            "Request",
            priority,
            on_request(rule, **kwargs),
            only_group=only_group,
        )
        self.matchers.append(str(mw))
        _loaded_matchers[mw.matcher] = mw
        return mw

    async def broadcast(self, msgs: Iterable | None, tag="", interval_time=0.5):
        if not msgs:
            return
        if isinstance(msgs, (str, OneBotV11Message, OneBotV11MessageSegment)):
            msgs = (msgs,)
        gdict = await self.get_enable_groups()
        for gid in gdict.keys():
            for bot in gdict[gid]:
                sid = int(bot.self_id)
                for msg in msgs:
                    await asyncio.sleep(interval_time)
                    try:
                        await send_to_target(bot, Target(str(gid)), msg)
                        self.logger.info(f"{sid}在群{gid}投递{tag}成功")
                    except Exception:
                        self.logger.error(f"{sid}在群{gid}投递{tag}失败")


class MatcherWrapper:
    """
    封装了 ``nonebot.matcher.Matcher`` ,使之可以受Service干预。

    并将 ``Matcher`` 常见的类方法进行了封装，如果需要其他类方法，请调用 ``.matcher.* ``
    """

    def __init__(
        self,
        sv: Service,
        type: str,
        priority: int,
        matcher: type[Matcher],
        log: bool = True,
        **info,
    ) -> None:
        self.matcher = matcher
        self.sv = sv
        self.priority = priority
        self.info = info
        self.type = type
        self.log = log

    def __getattr__(self, name: str):
        """Proxy unknown attributes to the underlying AlconnaMatcher/Matcher."""
        if "matcher" in self.__dict__:
            return getattr(self.__dict__["matcher"], name)
        raise AttributeError(name)

    @staticmethod
    def get_loaded_matchers() -> list[str]:
        return list(map(str, _loaded_matchers.values()))

    def handle(self, parameterless: list | None = None):
        def deco(func: T_Handler):
            return self.matcher.handle(parameterless)(func)

        return deco

    def __call__(self, func: T_Handler) -> T_Handler:
        return self.handle()(func)

    def receive(self, id: str = "", parameterless: list | None = None):
        def deco(func: T_Handler):
            return self.matcher.receive(id=id, parameterless=parameterless)(func)

        return deco

    def got(
        self,
        key: str,
        prompt: str | OneBotV11Message | OneBotV11MessageSegment | MessageTemplate | None = None,
        args_parser: T_Handler | None = None,
        parameterless: list | None = None,
    ):
        def deco(func: T_Handler):
            return self.matcher.got(key, prompt, parameterless, args_parser)(func)

        return deco

    async def reject(
        self,
        prompt: str | OneBotV11Message | OneBotV11MessageSegment | None = None,
        *,
        call_header: bool = False,
        at_sender: bool = False,
        **kwargs,
    ):
        if prompt:
            await self.send(
                prompt, call_header=call_header, at_sender=at_sender, **kwargs
            )
        raise RejectedException

    async def pause(
        self,
        prompt: str | OneBotV11Message | OneBotV11MessageSegment | None = None,
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
        message: str | OneBotV11Message | OneBotV11MessageSegment,
        *,
        call_header: bool = False,
        at_sender: bool = False,
        **kwargs,
    ):
        bot = current_bot.get()
        event = current_event.get()
        return await send_to_event(
            bot, event, message, at_sender=at_sender, call_header=call_header, **kwargs
        )

    async def send_uni(
        self,
        message,
        *,
        at_sender: bool = False,
        **kwargs,
    ):
        bot = current_bot.get()
        event = current_event.get()
        return await send_to_event(bot, event, message, at_sender=at_sender, **kwargs)

    async def finish(
        self,
        message: str | OneBotV11Message | OneBotV11MessageSegment | None = None,
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
async def _(_=Depends(log_matcherwrapper, use_cache=False)): ...
