"""Project command facade built on nonebot-plugin-alconna."""

from __future__ import annotations

from typing import Any

from nonebot_plugin_alconna import Alconna as Alconna
from nonebot_plugin_alconna import AlconnaMatches as AlconnaMatches
from nonebot_plugin_alconna import AlconnaResult as AlconnaResult
from nonebot_plugin_alconna import AlcResult as AlcResult
from nonebot_plugin_alconna import Args as Args
from nonebot_plugin_alconna import At as At
from nonebot_plugin_alconna import CommandMeta as CommandMeta
from nonebot_plugin_alconna import Match as Match
from nonebot_plugin_alconna import MsgId as MsgId
from nonebot_plugin_alconna import MsgTarget as MsgTarget
from nonebot_plugin_alconna import MultiVar as MultiVar
from nonebot_plugin_alconna import Option as Option
from nonebot_plugin_alconna import Query as Query
from nonebot_plugin_alconna import Reply as Reply
from nonebot_plugin_alconna import Subcommand as Subcommand
from nonebot_plugin_alconna import UniMsg as UniMsg
from nonebot_plugin_alconna import on_alconna as on_alconna
from nonebot_plugin_alconna.uniseg import UniMessage

UniTarget = MsgTarget


def uni_text(text: str) -> UniMessage:
    return UniMessage.text(text)


def uni_image(file: Any) -> UniMessage:
    if isinstance(file, bytes):
        return UniMessage.image(raw=file)
    if isinstance(file, str) and file.startswith(("http://", "https://")):
        return UniMessage.image(url=file)
    return UniMessage.image(path=file)


def uni_video(file: Any) -> UniMessage:
    if isinstance(file, bytes):
        return UniMessage.video(raw=file)
    if isinstance(file, str) and file.startswith(("http://", "https://")):
        return UniMessage.video(url=file)
    return UniMessage.video(path=file)


__all__ = [
    "AlcResult",
    "Alconna",
    "AlconnaMatches",
    "AlconnaResult",
    "Args",
    "At",
    "CommandMeta",
    "Match",
    "MsgId",
    "MsgTarget",
    "MultiVar",
    "Option",
    "Query",
    "Reply",
    "Subcommand",
    "UniMessage",
    "UniMsg",
    "UniTarget",
    "on_alconna",
    "uni_image",
    "uni_text",
    "uni_video",
]
