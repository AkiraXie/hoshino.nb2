from __future__ import annotations

import asyncio
import re
import os
import json
from collections import defaultdict
from typing import Iterable
import nonebot
from nonebot.params import Depends
from hoshino.core.hooks import run_preprocessor
from nonebot.exception import RejectedException, PausedException, FinishedException

from nonebot.rule import to_me
from nonebot.adapters import Bot
from nonebot.adapters import Event
from nonebot.matcher import Matcher, current_bot, current_event
from hoshino.platform.ob11.types import OneBotV11Message, OneBotV11MessageSegment
from hoshino import service_dir as _service_dir
from nonebot.plugin import (
    on_endswith,
    on_notice,
    on_request,
)
from hoshino.core.permission import ADMIN, NORMAL, OWNER, Permission, SUPERUSER
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
from nonebot_plugin_alconna import Alconna, Args, CommandMeta, on_alconna
from hoshino.core.logger_wrapper import LoggerWrapper


_illegal_char = re.compile(r'[\\/:*?"<>|\.!！]')
_loaded_services: dict[str, "Service"] = {}
_loaded_matchers: dict[str, "MatcherWrapper"] = {}


class MatcherWrapper:
    """AlconnaMatcher 代理 — 记录 sv_name，手写 API，支持 @mw 直接装饰"""

    def __init__(self, sv_name: str, matcher: Matcher):
        object.__setattr__(self, "_matcher", matcher)
        object.__setattr__(self, "sv_name", sv_name)

    @property
    def matcher(self) -> Matcher:
        return object.__getattribute__(self, "_matcher")

    def __call__(self, func):
        return self.matcher.handle()(func)

    # -- 代理 AlconnaMatcher 核心 API --

    def handle(self, parameterless=None):
        return self.matcher.handle(parameterless)

    def receive(self, id: str = "", parameterless=None):
        return self.matcher.receive(id, parameterless)

    def got(self, key: str, prompt=None, parameterless=None):
        return self.matcher.got(key, prompt, parameterless)

    async def send(self, message, *, at_sender=False, call_header=False, **kwargs):
        bot = current_bot.get()
        event = current_event.get()
        return await send_to_event(bot, event, message, at_sender=at_sender, call_header=call_header, **kwargs)

    async def finish(self, message=None, *, at_sender=False, call_header=False, **kwargs):
        if message:
            await self.send(message, at_sender=at_sender, call_header=call_header, **kwargs)
        raise FinishedException

    async def reject(self, prompt=None, *, at_sender=False, call_header=False, **kwargs):
        if prompt:
            await self.send(prompt, at_sender=at_sender, call_header=call_header, **kwargs)
        raise RejectedException

    async def pause(self, prompt=None, *, at_sender=False, call_header=False, **kwargs):
        if prompt:
            await self.send(prompt, at_sender=at_sender, call_header=call_header, **kwargs)
        raise PausedException

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

    # -- 辅助 --

    def set_arg(self, key: str, value):
        return self.matcher.set_arg(key, value)

    def get_arg(self, key: str, default=...):
        return self.matcher.get_arg(key, default)

    def __getattr__(self, name: str):
        # Fallback: 未显式代理的方法透传到 AlconnaMatcher
        return getattr(self.matcher, name)


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

    def get_config(self) -> dict:
        """读取服务配置 JSON → dict。无配置时返回空 dict。"""
        filename = os.path.join(_service_dir.parent, "service_config", f"{self.name}.json")
        try:
            with open(filename, encoding="utf8") as f:
                return json.load(f)
        except (Exception, FileNotFoundError):
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
        mw = MatcherWrapper(self.name, matcher)
        self.matchers.append(str(mw))
        _loaded_matchers[self.name] = mw
        return mw

    def on_command(
        self,
        name: str,
        only_to_me: bool = False,
        aliases: set | list | tuple | str | None = None,
        only_group: bool = True,
        permission: Permission = NORMAL,
        force_whitespace: bool | None = None,
        meta: CommandMeta | None = None,
        **kwargs,
    ):
        if isinstance(name, Alconna):
            alc = name
        else:
            alc = Alconna(name, Args["text", str], meta=meta) if meta else Alconna(name, Args["text", str])
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
        **kwargs,
    ):
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
            f"<Matcher from Service {self.name}, type=Message.alconna, command={command}>"
        )
        mw = MatcherWrapper(self.name, matcher)
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
        mw = MatcherWrapper(self.name, matcher)
        _loaded_matchers[self.name] = mw
        return mw

    def on_startswith(
        self,
        msg: str,
        only_to_me: bool = False,
        only_group: bool = True,
        permission: Permission = NORMAL,
        **kwargs,
    ):
        return self._on_alconna_delegate(
            re.compile(rf"{re.escape(msg)}.*"),
            "Message.startswith",
            only_to_me=only_to_me,
            only_group=only_group,
            permission=permission,
            **kwargs,
        )

    def on_endswith(
        self,
        msg: str,
        only_to_me: bool = False,
        only_group: bool = True,
        permission: Permission = NORMAL,
        **kwargs,
    ) -> "MatcherWrapper":
        # on_endswith 保留原生 — Alconna 按空格分词，无法匹配后缀
        kwargs["permission"] = permission
        rule = self.check_service(only_to_me, only_group)
        kwargs["rule"] = rule & kwargs.pop("rule", Rule())
        mw = MatcherWrapper(self.name, on_endswith(msg, **kwargs))
        self.matchers.append(str(mw))
        _loaded_matchers[self.name] = mw
        return mw

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
            return self.on_message(only_to_me=only_to_me, only_group=only_group, permission=permission, **kwargs)
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
        normal: bool = True,
        only_to_me: bool = False,
        only_group: bool = True,
        permission: Permission = NORMAL,
        **kwargs,
    ):
        kw_set = _iter_to_set(keywords)
        if not kw_set:
            return self.on_message(only_to_me=only_to_me, only_group=only_group, permission=permission, **kwargs)
        pattern = "|".join(re.escape(k) for k in sorted(kw_set))
        return self._on_alconna_delegate(
            re.compile(rf"^({pattern})$" if normal else rf"^({pattern})$"),
            "Message.fullmatch",
            only_to_me=only_to_me,
            only_group=only_group,
            permission=permission,
            **kwargs,
        )

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
    ):
        compiled = re.compile(pattern, flags)
        if full_match and not compiled.pattern.startswith("^"):
            compiled = re.compile(rf"^{pattern}", flags)
        return self._on_alconna_delegate(
            compiled,
            "Message.regex",
            only_to_me=only_to_me,
            only_group=only_group,
            permission=permission,
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
        return self._on_alconna_delegate(
            re.compile(r".+"),
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
        mw = MatcherWrapper(self.name, on_notice(rule=rule, permission=permission, **kwargs))
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
            sv.logger.info(f"Event was completed handling by <lc>{label}</>")
            return
    yield


@run_preprocessor
async def _(_=Depends(log_matcherwrapper, use_cache=False)): ...
