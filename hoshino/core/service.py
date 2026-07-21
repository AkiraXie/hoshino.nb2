from __future__ import annotations

import asyncio
import json
import os
import re
from collections import defaultdict
from typing import Callable, Iterable

import nonebot
from arclet.alconna import AllParam
from nonebot.adapters import Bot, Event
from nonebot.exception import FinishedException, PausedException, RejectedException
from nonebot.matcher import Matcher, current_bot, current_event
from nonebot.params import Depends
from nonebot.plugin import on_notice, on_request
from nonebot.rule import to_me
from nonebot_plugin_alconna import (
    Alconna,
    Args,
    CommandMeta,
    on_alconna,
)

from hoshino import service_dir as _service_dir
from hoshino.core.hooks import run_preprocessor
from hoshino.core.logger_wrapper import LoggerWrapper
from hoshino.core.permission import SUPERUSER, Permission
from hoshino.core.rule import (
    Rule,
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
from hoshino.platform.ob11.types import OneBotV11Message, OneBotV11MessageSegment
from hoshino.platform.permission import ADMIN, NORMAL, OWNER

_illegal_char = re.compile(r'[\\/:*?"<>|\.!！]')
_loaded_services: dict[str, "Service"] = {}
_loaded_matchers: dict[str, "MatcherWrapper"] = {}


class MatcherWrapper:
    """通用 Matcher 包装 — sv_name + handle/got/send/finish/reject/pause"""

    def __init__(self, sv_name: str, matcher: Matcher):
        self._matcher = matcher
        self.sv_name = sv_name

    @property
    def matcher(self) -> Matcher:
        return self._matcher

    @staticmethod
    def get_loaded_matchers() -> dict[str, "MatcherWrapper"]:
        return _loaded_matchers

    def __call__(self, func):
        return self.matcher.handle()(func)

    def handle(self, parameterless=None):
        return self.matcher.handle(parameterless)

    def receive(self, id: str = "", parameterless=None):
        return self.matcher.receive(id, parameterless)

    def got(self, key: str, prompt=None, parameterless=None):
        return self.matcher.got(key, prompt, parameterless)

    async def send(self, message, *, at_sender=False, call_header=False, **kwargs):
        bot = current_bot.get()
        event = current_event.get()
        return await send_to_event(
            bot, event, message, at_sender=at_sender, call_header=call_header, **kwargs
        )

    async def finish(
        self, message=None, *, at_sender=False, call_header=False, **kwargs
    ):
        if message:
            await self.send(
                message, at_sender=at_sender, call_header=call_header, **kwargs
            )
        raise FinishedException

    async def reject(
        self, prompt=None, *, at_sender=False, call_header=False, **kwargs
    ):
        if prompt:
            await self.send(
                prompt, at_sender=at_sender, call_header=call_header, **kwargs
            )
        raise RejectedException

    async def pause(self, prompt=None, *, at_sender=False, call_header=False, **kwargs):
        if prompt:
            await self.send(
                prompt, at_sender=at_sender, call_header=call_header, **kwargs
            )
        raise PausedException

    def set_arg(self, key: str, value):
        return self.matcher.set_arg(key, value)

    def get_arg(self, key: str, default=...):
        return self.matcher.get_arg(key, default)

    def __getattr__(self, name: str):
        return getattr(self.matcher, name)


class AlconnaMatcherWrapper(MatcherWrapper):
    """AlconnaMatcher 包装 — 增加 assign/dispatch/got_path 等 Alconna 特有方法"""

    def assign(self, path: str, value=None):
        return self.matcher.assign(path, value)

    def dispatch(self, path: str, *, template: str | None = None):
        return self.matcher.dispatch(path, template=template)

    def got_path(self, path: str, prompt=None, middleware=None):
        return self.matcher.got_path(path, prompt, middleware)

    def reject_path(self, path: str, prompt=None):
        return self.matcher.reject_path(path, prompt)

    def set_path_arg(self, key: str, value):
        return self.matcher.set_path_arg(key, value)

    def get_path_arg(self, key: str):
        return self.matcher.get_path_arg(key)


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


def _load_service_scopes(data: dict) -> tuple[set[str], set[str]]:
    """Load platform-scoped service state, accepting pre-platform OB11 data."""

    def scope_values(key: str) -> set[str]:
        values = data.get(key, [])
        return {str(value) for value in values} if isinstance(values, list) else set()

    enable_scope = scope_values("enable_scope")
    disable_scope = scope_values("disable_scope")

    # Older service files used bare group IDs. Those deployments were OB11-only,
    # so retain their state under the OB11 platform namespace. Explicit scoped
    # values win when a file contains both schemas.
    for group_id in data.get("enable_group", []):
        scope_key = group_scope_key(group_id)
        if scope_key not in disable_scope:
            enable_scope.add(scope_key)
    for group_id in data.get("disable_group", []):
        scope_key = group_scope_key(group_id)
        if scope_key not in enable_scope:
            disable_scope.add(scope_key)

    return enable_scope, disable_scope


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

        *`manage_perm` : 管理服务的权限，是一个 `Permission` 实例。
        `ADMIN`、`OWNER` 和 `SUPERUSER` 是允许的。

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
        self.enable_scope, self.disable_scope = _load_service_scopes(data)
        self.logger = LoggerWrapper(self.name)
        self.matchers = []

    @staticmethod
    def get_loaded_services() -> dict[str, "Service"]:
        return _loaded_services

    def set_enable(self, scope_key: str):
        self.enable_scope.add(scope_key)
        self.disable_scope.discard(scope_key)
        _save_service_data(self)

    def set_disable(self, scope_key: str):
        self.enable_scope.discard(scope_key)
        self.disable_scope.add(scope_key)
        _save_service_data(self)

    async def get_enable_groups(self) -> dict[int, list[Bot]]:
        gl = defaultdict(list)
        for bot in nonebot.get_bots().values():
            platform = platform_key(bot)
            sgl = set(g["group_id"] for g in await get_group_list(bot))
            if not sgl and platform == "telegram":
                prefix = f"{platform}:"
                sgl = {
                    int(scope.removeprefix(prefix))
                    for scope in self.enable_scope
                    if scope.startswith(prefix)
                    and scope.removeprefix(prefix).lstrip("-").isdigit()
                }
            if self.enable_on_default:
                sgl = {
                    gid
                    for gid in sgl
                    if group_scope_key(gid, platform=platform) not in self.disable_scope
                }
            else:
                sgl = {
                    gid
                    for gid in sgl
                    if group_scope_key(gid, platform=platform) in self.enable_scope
                }
            for g in sgl:
                gl[g].append(bot)
        return gl

    def get_config(self) -> dict:
        """读取服务配置 JSON → dict。无配置时返回空 dict。"""
        filename = os.path.join(
            _service_dir.parent, "service_config", f"{self.name}.json"
        )
        try:
            with open(filename, encoding="utf8") as f:
                return json.load(f)
        except (Exception, FileNotFoundError):
            return dict()

    def check_enabled(self, scope_key: str) -> bool:
        if scope_key in self.enable_scope:
            return True
        if scope_key in self.disable_scope:
            return False
        return bool(self.enable_on_default)

    def check_service(self, only_to_me: bool = False, only_group: bool = True) -> Rule:
        async def _cs(bot: Bot, event: Event) -> bool:
            group_id = get_group_id(event)
            if group_id is None:
                return not only_group
            return self.check_enabled(event_scope_key(bot, event))

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
        mw = AlconnaMatcherWrapper(self.name, matcher)
        self.matchers.append(str(mw))
        _loaded_matchers[self.name] = mw
        return mw

    def on_command(
        self,
        name: str | Alconna,
        only_to_me: bool = False,
        aliases: set | list | tuple | str | None = None,
        only_group: bool = True,
        permission: Permission = NORMAL,
        meta: CommandMeta | None = None,
        compact: bool = True,
        **kwargs,
    ):
        command_meta = meta if meta is not None else CommandMeta(compact=compact)
        if isinstance(name, Alconna):
            alc = name
        else:
            alc = Alconna(name, Args["text?", AllParam], meta=command_meta)
        alc_aliases: set[str] | tuple[str, ...] | None = None
        if aliases:
            if isinstance(aliases, str):
                alc_aliases = (aliases,)
            elif isinstance(aliases, (set, list, tuple)):
                alc_aliases = tuple(aliases)
        return self.on_alconna(
            alc,
            only_to_me=only_to_me,
            only_group=only_group,
            permission=permission,
            aliases=alc_aliases,
            meta=command_meta,
            compact=compact,
            **kwargs,
        )

    def on_alconna(
        self,
        command: Alconna | str,
        *,
        only_to_me: bool = False,
        only_group: bool = True,
        permission: Permission = NORMAL,
        aliases: set[str] | tuple[str, ...] | None = None,
        compact: bool = True,
        meta: CommandMeta | None = None,
        **kwargs,
    ):
        command_meta = meta if meta is not None else CommandMeta(compact=compact)
        if isinstance(command, Alconna):
            if command_meta is not command.meta:
                command += command_meta
        else:
            command = Alconna(command, meta=command_meta)
        kwargs["permission"] = permission
        rule = self.check_service(only_to_me, only_group)
        kwargs["rule"] = rule & kwargs.pop("rule", Rule())
        matcher = on_alconna(command, aliases=aliases, **kwargs)
        matcher.__hoshino_info__ = {
            "service": self.name,
            "type": "Message.alconna",
            "command": str(command),
            "only_group": only_group,
        }
        self.matchers.append(
            f"<Matcher from Service {self.name}, type=Message.alconna, "
            f"command={command}>"
        )
        mw = AlconnaMatcherWrapper(self.name, matcher)
        _loaded_matchers[self.name] = mw
        return mw

    def _on_alconna_delegate(
        self,
        command: Alconna | str | re.Pattern,
        type_label: str,
        only_to_me: bool = False,
        only_group: bool = True,
        permission: Permission = NORMAL,
        aliases: set[str] | tuple[str, ...] | None = None,
        **kwargs,
    ):
        if not isinstance(command, Alconna):
            command = Alconna(command)
        kwargs["permission"] = permission
        rule = self.check_service(only_to_me, only_group)
        kwargs["rule"] = rule & kwargs.pop("rule", Rule())
        matcher = on_alconna(command, aliases=aliases, **kwargs)
        matcher.__hoshino_info__ = {
            "service": self.name,
            "type": type_label,
            "command": str(command),
            "only_group": only_group,
        }
        self.matchers.append(
            f"<Matcher from Service {self.name}, type={type_label}, command={command}>"
        )
        mw = AlconnaMatcherWrapper(self.name, matcher)
        _loaded_matchers[self.name] = mw
        return mw

    def _on_native_message(
        self,
        matcher_factory: Callable[..., type[Matcher]],
        type_label: str,
        command: str = "",
        *,
        matcher_args: tuple[object, ...] = (),
        only_to_me: bool = False,
        only_group: bool = True,
        permission: Permission = NORMAL,
        **kwargs,
    ) -> "MatcherWrapper":
        kwargs["permission"] = permission
        rule = self.check_service(only_to_me, only_group)
        kwargs["rule"] = rule & kwargs.pop("rule", Rule())
        matcher = matcher_factory(*matcher_args, **kwargs)
        matcher.__hoshino_info__ = {
            "service": self.name,
            "type": type_label,
            "command": command,
            "only_group": only_group,
        }
        description = f"<Matcher from Service {self.name}, type={type_label}"
        if command:
            description += f", command={command}"
        self.matchers.append(f"{description}>")
        mw = MatcherWrapper(self.name, matcher)
        _loaded_matchers[self.name] = mw
        return mw

    def on_startswith(
        self,
        msg: str,
        only_to_me: bool = False,
        only_group: bool = True,
        permission: Permission = NORMAL,
        ignorecase: bool = False,
        **kwargs,
    ):
        return self._on_native_message(
            nonebot.on_startswith,
            "Message.startswith",
            msg,
            matcher_args=(msg,),
            only_to_me=only_to_me,
            only_group=only_group,
            permission=permission,
            ignorecase=ignorecase,
            **kwargs,
        )

    def on_endswith(
        self,
        msg: str,
        only_to_me: bool = False,
        only_group: bool = True,
        permission: Permission = NORMAL,
        ignorecase: bool = False,
        **kwargs,
    ) -> "MatcherWrapper":
        return self._on_native_message(
            nonebot.on_endswith,
            "Message.endswith",
            msg,
            matcher_args=(msg,),
            only_to_me=only_to_me,
            only_group=only_group,
            permission=permission,
            ignorecase=ignorecase,
            **kwargs,
        )

    def on_keyword(
        self,
        keywords: set | list | tuple | str | None,
        normal: bool = True,
        only_to_me: bool = False,
        only_group: bool = True,
        permission: Permission = NORMAL,
        **kwargs,
    ):
        kw_set = _iter_to_set(keywords)
        if not kw_set:
            return self.on_message(
                only_to_me=only_to_me,
                only_group=only_group,
                permission=permission,
                **kwargs,
            )
        pattern = "|".join(re.escape(k) for k in sorted(kw_set))
        pattern = pattern if normal else rf"(?:^|\W)({pattern})(?:$|\W)"
        return self._on_alconna_delegate(
            re.compile(pattern),
            "Message.keyword",
            only_to_me=only_to_me,
            only_group=only_group,
            permission=permission,
            **kwargs,
        )

    def on_fullmatch(
        self,
        keywords: set | list | tuple | str | None,
        ignorecase: bool = False,
        only_to_me: bool = False,
        only_group: bool = True,
        permission: Permission = NORMAL,
        **kwargs,
    ):
        kw_set = _iter_to_set(keywords)
        if not kw_set:
            return self.on_message(
                only_to_me=only_to_me,
                only_group=only_group,
                permission=permission,
                **kwargs,
            )
        messages = tuple(sorted(kw_set))
        return self._on_native_message(
            nonebot.on_fullmatch,
            "Message.fullmatch",
            "|".join(messages),
            matcher_args=(messages,),
            only_to_me=only_to_me,
            only_group=only_group,
            permission=permission,
            ignorecase=ignorecase,
            **kwargs,
        )

    def on_regex(
        self,
        pattern: str,
        flags: int | re.RegexFlag = 0,
        only_to_me: bool = False,
        only_group: bool = True,
        permission: Permission = NORMAL,
        **kwargs,
    ):
        return self._on_native_message(
            nonebot.on_regex,
            "Message.regex",
            pattern,
            matcher_args=(pattern,),
            only_to_me=only_to_me,
            only_group=only_group,
            permission=permission,
            flags=flags,
            **kwargs,
        )

    def on_message(
        self,
        only_to_me: bool = False,
        only_group: bool = True,
        permission: Permission = NORMAL,
        log: bool = False,
        **kwargs,
    ):
        return self._on_native_message(
            nonebot.on_message,
            "Message.message",
            only_to_me=only_to_me,
            only_group=only_group,
            permission=permission,
            **kwargs,
        )

    def on_notice(
        self, rule: Rule = Rule(), only_group: bool = True, permission=NORMAL, **kwargs
    ) -> "MatcherWrapper":
        rule = self.check_service(False, only_group) & rule
        mw = MatcherWrapper(
            self.name, on_notice(rule=rule, permission=permission, **kwargs)
        )
        self.matchers.append(str(mw))
        _loaded_matchers[self.name] = mw
        return mw

    def on_request(self, only_group: bool = True, **kwargs) -> "MatcherWrapper":
        rule = self.check_service(False, only_group) & kwargs.pop("rule", Rule())
        mw = MatcherWrapper(self.name, on_request(rule, **kwargs))
        self.matchers.append(str(mw))
        _loaded_matchers[self.name] = mw
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


async def log_matcherwrapper(matcher: Matcher):
    info = getattr(matcher, "__hoshino_info__", None)
    if info is not None:
        sv_name = info.get("service", "?")
        label = info.get("type", "?") + ":" + info.get("command", "?")
        sv = _loaded_services.get(sv_name)
        if sv is not None:
            sv.logger.info(f"Event will be handled by <lc>{label}</>")
            yield
            sv.logger.info(f"Event was completed by <lc>{label}</>")
            return
    yield


@run_preprocessor
async def _(_=Depends(log_matcherwrapper, use_cache=False)): ...
