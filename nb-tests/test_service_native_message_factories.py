"""Service non-command message factories use native NoneBot matchers."""

import pytest
from test_command_adapters import _ob11_group_message


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_service_message_factories_match_complete_native_messages():
    from hoshino.service import MatcherWrapper, Service

    service = Service("test_native_message_factories", visible=False)
    cases = (
        (service.on_startswith("HELLO", ignorecase=True), "hello world"),
        (service.on_endswith("WORLD", ignorecase=True), "hello world"),
        (service.on_fullmatch("HELLO WORLD", ignorecase=True), "hello world"),
        (service.on_regex(r"world"), "hello world"),
        (service.on_message(), "any complete message"),
    )

    try:
        for wrapper, text in cases:
            bot, event = _ob11_group_message(text, to_me=False)

            assert type(wrapper) is MatcherWrapper
            assert await wrapper.matcher.rule(bot, event, {})
    finally:
        for wrapper, _ in cases:
            wrapper.matcher.destroy()
