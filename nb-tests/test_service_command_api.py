"""Service command facade metadata and compact parsing behavior."""

import asyncio

import pytest
from nonebot_plugin_alconna.uniseg import UniMessage


@pytest.mark.usefixtures("_nonebot_bootstrap")
def test_on_command_defaults_to_compact_parsing():
    from hoshino.service import Service

    matcher = Service("test_command_compact", visible=False).on_command("testcompact")
    command = matcher.matcher.command()

    result = command.parse("testcompactvalue")

    assert command.meta.compact is True
    assert result.matched
    assert UniMessage(result.all_matched_args["text"]).extract_plain_text() == "value"


@pytest.mark.usefixtures("_nonebot_bootstrap")
def test_on_command_captures_the_complete_argument_tail():
    from hoshino.platform.depends import ParamMessage, ParamText
    from hoshino.service import Service

    matcher = Service("test_command_all_params", visible=False).on_command(
        "testparams", compact=False
    )
    command = matcher.matcher.command()

    result = command.parse("testparams a b c")

    assert result.matched
    assert UniMessage(result.all_matched_args["text"]).extract_plain_text() == "a b c"
    assert asyncio.run(ParamText().dependency(result)) == "a b c"

    no_argument = command.parse("testparams")
    assert no_argument.matched
    assert asyncio.run(ParamText(default="fallback").dependency(no_argument)) == "fallback"

    message_result = command.parse(
        UniMessage.text("testparams question你答answer")
        + UniMessage.image(url="https://example.com/image.png")
        + UniMessage.text("tail")
    )
    argument_message = asyncio.run(ParamMessage().dependency(message_result))
    assert [segment.type for segment in argument_message] == ["text", "image", "text"]


@pytest.mark.usefixtures("_nonebot_bootstrap")
def test_on_command_explicit_meta_takes_precedence_over_compact():
    from hoshino.command import CommandMeta
    from hoshino.service import Service

    meta = CommandMeta(description="explicit metadata", compact=False)
    matcher = Service("test_command_meta", visible=False).on_command(
        "testmeta", meta=meta, compact=True
    )
    command = matcher.matcher.command()

    assert command.meta is meta
    assert command.meta.compact is False
    assert not command.parse("testmetavalue").matched
    assert "explicit metadata" in command.get_help()


@pytest.mark.usefixtures("_nonebot_bootstrap")
def test_on_alconna_creates_compact_meta_when_none_is_provided():
    from hoshino.command import Alconna, Args, CommandMeta
    from hoshino.service import Service

    command = Alconna(
        "testexistingmeta",
        Args["value", str],
        meta=CommandMeta(description="old metadata", compact=False),
    )

    Service("test_alconna_existing_meta", visible=False).on_alconna(command)

    result = command.parse("testexistingmetavalue")
    assert command.meta.description == "Unknown"
    assert command.meta.compact is True
    assert result.matched
    assert result.all_matched_args == {"value": "value"}
    assert "old metadata" not in command.get_help()


@pytest.mark.usefixtures("_nonebot_bootstrap")
def test_on_alconna_explicit_meta_replaces_existing_metadata():
    from hoshino.command import Alconna, Args, CommandMeta
    from hoshino.service import Service

    command = Alconna(
        "testreplacemeta",
        Args["value", str],
        meta=CommandMeta(description="old metadata"),
    )
    meta = CommandMeta(description="new metadata", compact=False)

    Service("test_alconna_replace_meta", visible=False).on_alconna(
        command, meta=meta, compact=True
    )

    assert command.meta is meta
    assert command.meta.compact is False
    assert not command.parse("testreplacemetavalue").matched
    assert "new metadata" in command.get_help()
    assert "old metadata" not in command.get_help()


@pytest.mark.usefixtures("_nonebot_bootstrap")
def test_on_command_compact_can_be_disabled():
    from hoshino.service import Service

    matcher = Service("test_compact_disabled", visible=False).on_command(
        "testwhitespace", compact=False
    )
    command = matcher.matcher.command()

    assert command.meta.compact is False
    assert not command.parse("testwhitespacevalue").matched
    assert command.parse("testwhitespace value").matched
