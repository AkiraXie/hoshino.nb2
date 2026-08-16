"""Legacy NoneBot command helpers."""

from __future__ import annotations

from asyncio import get_running_loop
from collections.abc import Sequence

import nonebot
from nonebot.adapters import Bot, Event
from nonebot.matcher import Matcher
from nonebot.params import Depends
from nonebot.permission import SUPERUSER
from nonebot.plugin import CommandGroup, on_command, on_message
from nonebot.rule import Rule, to_me
from nonebot.typing import T_State

from hoshino.platform import get_event_message, get_session_id, get_user_id


def Cooldown(cooldown: float = 10, prompt: str | None = None) -> None:
    debounced = set()

    async def dependency(matcher: Matcher, event: Event, bot: Bot):
        loop = get_running_loop()
        key = get_user_id(event) or get_session_id(event) or str(id(event))
        message = prompt.format(cooldown) if prompt else f"请稍等 {cooldown} 秒后再试。"
        if key in debounced:
            await matcher.finish(message=message)
        debounced.add(key)
        loop.call_later(cooldown, lambda: debounced.discard(key))

    return Depends(dependency)


def get_bot_list() -> Sequence[Bot]:
    return list(nonebot.get_bots().values())


async def _strip_cmd(bot: Bot, event: Event, state: T_State) -> None:
    message = get_event_message(event)
    segment = message.pop(0)
    segment_text = str(segment).lstrip()
    new_message = message.__class__(segment_text[len(state["_prefix"]["raw_command"]) :].lstrip())
    for new_segment in reversed(new_message):
        message.insert(0, new_segment)


def sucmd(
    name: str,
    only_to_me: bool = True,
    aliases: set | None = None,
    **kwargs,
) -> type[Matcher]:
    kwargs["aliases"] = aliases
    kwargs["permission"] = SUPERUSER
    kwargs["rule"] = to_me() if only_to_me else Rule()
    handlers = kwargs.pop("handlers", [])
    handlers.insert(0, _strip_cmd)
    kwargs["handlers"] = handlers
    kwargs.setdefault("block", True)
    kwargs["cmd"] = name
    return on_command(**kwargs)


def sucmds(name: str, only_to_me: bool = False, **kwargs) -> CommandGroup:
    kwargs["permission"] = SUPERUSER
    kwargs["rule"] = to_me() if only_to_me else Rule()
    handlers = kwargs.pop("handlers", [])
    handlers.insert(0, _strip_cmd)
    kwargs["handlers"] = handlers
    kwargs.setdefault("block", True)
    return CommandGroup(name, **kwargs)


def sumsg(
    only_to_me: bool = True,
    rule: Rule = Rule(),
    **kwargs,
) -> type[Matcher]:
    kwargs["permission"] = SUPERUSER
    kwargs["rule"] = rule & to_me() if only_to_me else Rule(rule)
    kwargs.setdefault("block", True)
    return on_message(**kwargs)


__all__ = ["Cooldown", "get_bot_list", "sucmd", "sucmds", "sumsg"]
