"""Representative non-Alconna entry points across supported adapters."""

from types import SimpleNamespace

import pytest
from nonebot.matcher import matchers
from nonebot.rule import TrieRule

from adapter_events import ob11_group_message, telegram_group_message


def _matcher_for_handler(handler):
    for matcher_group in matchers.values():
        for matcher in matcher_group:
            if any(dependent.call is handler for dependent in matcher.handlers):
                return matcher
    raise AssertionError(f"No matcher registered for {handler.__module__}.{handler.__name__}")


async def _native_command_rule_matches(matcher, bot, event) -> bool:
    state = {}
    TrieRule.get_value(bot, event, state)
    return await matcher.rule(bot, event, state)


@pytest.mark.usefixtures("_nonebot_bootstrap")
@pytest.mark.parametrize("factory", (ob11_group_message, telegram_group_message))
async def test_image_delete_command_rule_accepts_both_adapters(factory):
    """Image management's native command reaches its matcher rule on both adapters."""
    from hoshino.base.image import delete_img_cmd

    matcher = _matcher_for_handler(delete_img_cmd)
    bot, event = factory("删图 example.jpg", to_me=True)
    assert await _native_command_rule_matches(matcher, bot, event)


@pytest.mark.usefixtures("_nonebot_bootstrap")
@pytest.mark.parametrize("factory", (ob11_group_message, telegram_group_message))
async def test_resolve_rule_recognizes_bilibili_links_on_both_adapters(factory):
    """Resolver message-rule routing works for native messages from both adapters."""
    from hoshino.modules.information.resolve import check_json_or_text

    _bot, event = factory("https://b23.tv/abc123", to_me=False)
    state = {}
    assert await check_json_or_text(event, state)
    assert state["__url_name"] == "b23"


@pytest.mark.usefixtures("_nonebot_bootstrap")
@pytest.mark.parametrize("factory", (ob11_group_message, telegram_group_message))
async def test_listenmeta_bot_connect_notifies_superusers_on_both_adapters(factory, monkeypatch):
    """The bot-connect lifecycle hook emits the expected private notification."""
    from hoshino.base import listenmeta

    sent = []

    async def capture_send(bot, target, message):
        sent.append((bot, target, message))

    monkeypatch.setattr(listenmeta, "config", SimpleNamespace(superusers={"42"}))
    monkeypatch.setattr(listenmeta, "send_to_target", capture_send)
    bot, _event = factory("ignored", to_me=False)

    await listenmeta._(bot)

    assert len(sent) == 1
    assert sent[0][0] is bot
    assert sent[0][1].id == "42"
    assert sent[0][1].private
    assert sent[0][2] == "生命周期上线~"


@pytest.mark.usefixtures("_nonebot_bootstrap")
@pytest.mark.parametrize("factory", (ob11_group_message, telegram_group_message))
async def test_healthcheck_reports_adapter_bot_connectivity(factory, monkeypatch):
    """The health endpoint verifies group-list access through the platform wrapper."""
    from hoshino.modules.develop import healthchecker

    async def fake_group_list(bot):
        assert bot is expected_bot
        return []

    expected_bot, _event = factory("ignored", to_me=False)
    monkeypatch.setattr(healthchecker.nonebot, "get_bot", lambda _bot_id=None: expected_bot)
    monkeypatch.setattr(healthchecker, "get_group_list", fake_group_list)

    response = await healthchecker.bot_check("10000")

    assert response.status_code == 200
    assert response.body == b'{"status":"ok","message":"get bot ok: 10000"}'
