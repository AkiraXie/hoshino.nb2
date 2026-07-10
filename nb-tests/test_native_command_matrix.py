"""Cross-adapter rule checks for plugins using native NoneBot commands."""

import pytest
from nonebug import App

from test_command_adapters import _ob11_group_message, _telegram_group_message


def _native_commands():
    # Imports must follow the shared NoneBot bootstrap fixture.
    from hoshino.base import broadcast, cookies, ls, test, zai
    from hoshino.base import black
    from hoshino.modules.develop import server_info

    return (
        ("black", black.lahei, "拉黑"),
        (
            "cookies",
            _matcher_for_handler(cookies.check_cookies_cmd),
            "check_cookies",
        ),
        ("ls", ls.cmd_am, "ls.allmatcher"),
        ("zai", zai.zai, "zai"),
        ("broadcast", broadcast.bc, "bc hello"),
        ("test", test.test1, "testgetbot"),
        ("server_info", server_info.showcmd, "状态"),
    )


def _matcher_for_handler(handler):
    from nonebot.matcher import matchers

    for matcher_group in matchers.values():
        for matcher in matcher_group:
            if any(dependent.call is handler for dependent in matcher.handlers):
                return matcher
    raise AssertionError(f"No matcher registered for {handler.__module__}.{handler.__name__}")


def _fake_bot(ctx, bot):
    kwargs = {"config": bot.bot_config} if bot.adapter.get_name() == "Telegram" else {}
    return ctx.create_bot(
        base=type(bot),
        adapter=bot.adapter,
        self_id=bot.self_id,
        auto_connect=False,
        **kwargs,
    )


def _prepare_response(plugin, monkeypatch):
    from hoshino.base import broadcast, cookies, ls, test, zai
    from hoshino.modules.develop import server_info

    if plugin == "black":
        return "请输入要拉黑的id,并用空格隔开~\n在群聊中，还支持直接at哦~", "reject"
    if plugin == "cookies":
        monkeypatch.setattr(cookies, "check_all_cookies", lambda: {})
        return "没有可用的cookies", None
    if plugin == "ls":
        expected = ["该bot注册的matcher_wrapper如下:"]
        expected.extend(ls.MatcherWrapper.get_loaded_matchers())
        return "\n".join(expected), "finish"
    if plugin == "zai":
        monkeypatch.setattr(zai.config, "zai", "test-zai")
        return "test-zai", "finish"
    if plugin == "broadcast":
        async def empty_group_list(_bot):
            return []

        monkeypatch.setattr(broadcast, "get_group_list", empty_group_list)
        return "广播完成,投递成功0个群", "finish"
    if plugin == "test":
        monkeypatch.setattr(test, "get_bot_list", lambda: ["test-bot"])
        return "['test-bot']", "finish"
    if plugin == "server_info":
        async def fake_stat():
            return "test status"

        monkeypatch.setattr(server_info, "get_stat", fake_stat)
        return "test status", "finish"
    raise AssertionError(f"Unknown native command case: {plugin}")


@pytest.mark.usefixtures("_nonebot_bootstrap")
@pytest.mark.parametrize("factory", (_ob11_group_message, _telegram_group_message))
@pytest.mark.parametrize("case_index", range(7))
async def test_native_command_rule_accepts_both_adapters(
    app: App, factory, case_index, monkeypatch
):
    plugin, matcher, sample = _native_commands()[case_index]
    bot, event = factory(sample, to_me=True)

    async with app.test_matcher(matcher) as ctx:
        bot = _fake_bot(ctx, bot)
        response, action = _prepare_response(plugin, monkeypatch)
        ctx.receive_event(bot, event)
        ctx.should_ignore_permission(matcher)
        ctx.should_pass_rule(matcher)
        send_kwargs = (
            {"call_header": False, "at_sender": False}
            if plugin == "cookies"
            else {}
        )
        ctx.should_call_send(event, response, bot=bot, **send_kwargs)
        if action == "reject":
            ctx.should_rejected(matcher)
        elif action == "finish":
            ctx.should_finished(matcher)
