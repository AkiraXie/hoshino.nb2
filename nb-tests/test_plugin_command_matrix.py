"""Representative OB11/Telegram command parsing for every Alconna service."""

from re import Pattern

import pytest
from arclet.alconna import command_manager
from nonebot.matcher import current_bot
from test_command_adapters import _ob11_group_message, _telegram_group_message

COMMAND_SAMPLES = (
    ("help", "help", "help"),
    ("service_manage", "enable", "enable dice"),
    ("bilireq", "本群动态订阅", "本群动态订阅"),
    ("weibo", "微博订阅", "微博订阅"),
    ("pushlive", "直播订阅", "直播订阅"),
    ("QA", "看看我问", "看看我问"),
    ("alisten", "播放列表", "播放列表"),
    ("emojimix", "testemoji", "testemoji"),
    ("foods", r"^(.{0,9})吃(什么|啥)", "今天吃什么"),
    ("qbitorrent", "下载列表", "下载列表"),
    ("steam", "steam订阅列表", "steam订阅列表"),
    ("b64", "b64加密", "b64加密 hello"),
    ("nbnhhsh", r"^[\?\？]{1,2} ?([a-z0-9]+)$", "?nb"),
    ("echoandsay", "echo", "echo hello"),
    ("coser", "coser", "coser"),
    ("dice", r"^.r(\d{1,2})d(\d{1,3})([+-]\d{1,3})?", ".r1d6"),
    ("bihua", "随机壁画", "随机壁画"),
)


def _command_named(name: str):
    for command in command_manager.get_commands():
        header = command.command
        if isinstance(header, Pattern):
            if header.pattern == name:
                return command
        elif str(header) == name:
            return command
    return None


@pytest.mark.usefixtures("_nonebot_bootstrap")
@pytest.mark.parametrize("factory", (_ob11_group_message, _telegram_group_message))
@pytest.mark.parametrize(("plugin", "command_name", "sample"), COMMAND_SAMPLES)
def test_representative_command_parses_on_both_adapters(
    plugin, command_name, sample, factory
):
    """Each command service accepts its representative adapter-native message."""
    bot, event = factory(sample, to_me=True)
    token = current_bot.set(bot)
    try:
        command = _command_named(command_name)
        matched = command is not None and command.parse(event.get_message()).matched
    finally:
        current_bot.reset(token)

    assert matched, f"{plugin} did not parse {sample!r} from {bot.adapter.get_name()}"
