from loguru import logger

from hoshino.core.log import Filter


def _record(
    message: str, *, name: str = "hoshino.modules.example", level: str = "INFO"
) -> dict:
    return {
        "name": name,
        "message": message,
        "level": logger.level(level),
    }


def test_filter_allows_hoshino_matcher_log():
    record = _record("resolve | Event will be handled by Message.message")

    assert Filter()(record) is True
    assert record["name"] == "hoshino"


def test_filter_hides_nonebot_hoshino_matcher_lifecycle():
    matcher = "Matcher(type='message', module=hoshino.core.service, lineno=466)"

    assert not Filter()(
        _record(f"Event will be handled by {matcher}", name="nonebot.message")
    )
    assert not Filter()(_record(f"{matcher} running complete", name="nonebot.message"))


def test_filter_hides_nonebot_hoshino_alconna_matcher_lifecycle():
    matcher = (
        "AlconnaMatcher(type='', command=Alconna::微博订阅, "
        "module=hoshino.core.service, lineno=407)"
    )

    assert not Filter()(_record(f"{matcher} running complete", name="nonebot.matcher"))


def test_filter_keeps_other_nonebot_logs_and_matcher_errors():
    hoshino_matcher = "Matcher(type='message', module=hoshino.core.service, lineno=466)"
    plugin_matcher = "Matcher(type='message', module=another.plugin, lineno=12)"

    assert Filter()(_record("Bot connected", name="nonebot"))
    assert Filter()(
        _record(f"Event will be handled by {plugin_matcher}", name="nonebot")
    )
    assert Filter()(
        _record(
            f"Rule check failed for {hoshino_matcher}.",
            name="nonebot",
            level="ERROR",
        )
    )


def test_filter_applies_log_level():
    log_filter = Filter()
    log_filter.level = "INFO"

    assert not log_filter(_record("debug detail", level="DEBUG"))
