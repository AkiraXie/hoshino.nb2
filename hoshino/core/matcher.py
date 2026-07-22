from __future__ import annotations

from collections.abc import AsyncIterator

from nonebot.exception import FinishedException, PausedException, RejectedException
from nonebot.matcher import Matcher, current_bot, current_event
from nonebot.params import Depends

from hoshino.core.hooks import run_preprocessor
from hoshino.core.logger_wrapper import LoggerWrapper
from hoshino.platform import send_to_event


class MatcherWrapper:
    """Hoshino service context and convenience methods around a NoneBot matcher."""

    def __init__(self, sv_name: str, matcher: Matcher):
        self._matcher = matcher
        self.sv_name = sv_name

    @property
    def matcher(self) -> Matcher:
        return self._matcher

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
    """Matcher wrapper exposing Alconna-specific handler helpers."""

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


async def log_matcher(matcher: Matcher) -> AsyncIterator[None]:
    info = getattr(matcher, "__hoshino_info__", None)
    if info is None:
        yield
        return

    logger = LoggerWrapper(info.get("service", "?"))
    label = f"{info.get('type', '?')}:{info.get('command', '?')}"
    logger.info(f"Event will be handled by <lc>{label}</>")
    yield
    logger.info(f"Event was completed by <lc>{label}</>")


@run_preprocessor
async def log_matcher_hook(
    _=Depends(log_matcher, use_cache=False),
) -> None: ...
