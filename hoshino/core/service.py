from __future__ import annotations

import json
import os
import re
from collections import defaultdict
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Callable, Generic, TypeVar, cast

import nonebot
from arclet.alconna import AllParam
from nonebot.adapters import Bot, Event
from nonebot.matcher import Matcher
from nonebot.plugin import on_notice, on_request
from nonebot.rule import to_me
from pydantic import TypeAdapter, ValidationError
from nonebot_plugin_alconna import (
    Alconna,
    Args,
    CommandMeta,
    on_alconna,
)

from hoshino import service_dir as _service_dir
from hoshino.core.logger_wrapper import LoggerWrapper
from hoshino.core.matcher import (
    AlconnaMatcherWrapper,
    MatcherWrapper,
)
from hoshino.core.permission import SUPERUSER, Permission
from hoshino.core.rule import (
    Rule,
)
from hoshino.platform import (
    event_scope_key,
    get_group_id,
    get_group_list,
    group_scope_key,
    platform_key,
)
from hoshino.platform.permission import ADMIN, NORMAL, OWNER

_illegal_char = re.compile(r'[\\/:*?"<>|\.!！]')
ConfigT = TypeVar("ConfigT")
_loaded_services: dict[str, "Service[Any]"] = {}
_service_config_dir = Path(__file__).resolve().parent.parent / "service_config"


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


def _save_service_data(service: "Service[Any]"):
    _service_dir.mkdir(parents=True, exist_ok=True)
    data_file = _service_dir / f"{service.name}.json"
    temporary = data_file.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(
            {
                "name": service.name,
                "enable_scope": sorted(service.enable_scope),
                "disable_scope": sorted(service.disable_scope),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf8",
    )
    temporary.replace(data_file)


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


def _service_config_file(service_name: str) -> Path:
    return _service_config_dir / f"{service_name}.json"


def _config_to_json_data(config: object) -> object:
    if is_dataclass(config):
        return asdict(config)
    if hasattr(config, "model_dump"):
        return config.model_dump()  # type: ignore[no-any-return, attr-defined]
    if hasattr(config, "__dict__"):
        return vars(config)
    return config


class Service(Generic[ConfigT]):
    def __init__(
        self,
        name: str,
        manage_perm: Permission = ADMIN,
        enable_on_default: bool = True,
        visible: bool = True,
        config_type: type[ConfigT] | None = None,
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
        self.config_type = config_type
        assert self.name not in _loaded_services, (
            f'Service name "{self.name}" already exist!'
        )
        data = _load_service_data(self.name)
        self.enable_scope, self.disable_scope = _load_service_scopes(data)
        self.logger = LoggerWrapper(self.name)
        self.matchers = []
        self._enable_groups_cache: dict[int, list[Bot]] | None = None
        self._ensure_default_config()
        _loaded_services[self.name] = self

    @staticmethod
    def get_loaded_services() -> dict[str, "Service[Any]"]:
        return _loaded_services

    def set_enable(self, scope_key: str):
        self.enable_scope.add(scope_key)
        self.disable_scope.discard(scope_key)
        self._enable_groups_cache = None
        _save_service_data(self)

    def set_disable(self, scope_key: str):
        self.enable_scope.discard(scope_key)
        self.disable_scope.add(scope_key)
        self._enable_groups_cache = None
        _save_service_data(self)

    async def get_enable_groups(self) -> dict[int, list[Bot]]:
        if self._enable_groups_cache is not None:
            return self._enable_groups_cache
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
        self._enable_groups_cache = dict(gl)
        return self._enable_groups_cache

    def _ensure_default_config(self) -> None:
        if self.config_type is None:
            return
        filename = _service_config_file(self.name)
        if filename.exists():
            return
        default_config = self.config_type()
        filename.parent.mkdir(parents=True, exist_ok=True)
        temporary = filename.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(
                _config_to_json_data(default_config),
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf8",
        )
        temporary.replace(filename)

    def get_config(self) -> ConfigT:
        """读取服务配置。绑定 config_type 时返回该类型，否则返回 dict。"""
        filename = _service_config_file(self.name)
        try:
            with open(filename, encoding="utf8") as f:
                raw_config = json.load(f)
        except FileNotFoundError:
            if self.config_type is None:
                return cast(ConfigT, {})
            self._ensure_default_config()
            return self.config_type()
        except json.JSONDecodeError as exc:
            if self.config_type is None:
                return cast(ConfigT, {})
            raise ValueError(f"Invalid JSON in service config {filename}") from exc

        if self.config_type is None:
            return cast(ConfigT, raw_config if isinstance(raw_config, dict) else {})
        try:
            return TypeAdapter(self.config_type).validate_python(raw_config)
        except ValidationError as exc:
            raise ValueError(f"Invalid service config {filename}") from exc

    def save_config(self, config: ConfigT) -> None:
        """写回服务配置。

        用现有 ``TypeAdapter`` 校验后，以与 ``_ensure_default_config`` 相同的
        序列化格式原子写入 ``hoshino/service_config/<name>.json``。
        """
        if self.config_type is not None:
            validated = TypeAdapter(self.config_type).validate_python(config)
        else:
            validated = config
        filename = _service_config_file(self.name)
        filename.parent.mkdir(parents=True, exist_ok=True)
        temporary = filename.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(
                _config_to_json_data(validated),
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf8",
        )
        temporary.replace(filename)

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
        kwargs["block"] = kwargs.get("block", True)
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
        return mw

    def on_request(self, only_group: bool = True, **kwargs) -> "MatcherWrapper":
        rule = self.check_service(False, only_group) & kwargs.pop("rule", Rule())
        mw = MatcherWrapper(self.name, on_request(rule, **kwargs))
        self.matchers.append(str(mw))
        return mw
