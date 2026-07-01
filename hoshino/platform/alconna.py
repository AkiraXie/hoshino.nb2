"""Compatibility exports for the old hoshino.platform.alconna path."""

from hoshino.command import (
    Alconna as Alconna,
    AlconnaMatches as AlconnaMatches,
    AlconnaResult as AlconnaResult,
    Args as Args,
    CommandMeta as CommandMeta,
    Match as Match,
    MsgId as MsgId,
    MsgTarget as MsgTarget,
    Option as Option,
    Query as Query,
    Reply as Reply,
    Subcommand as Subcommand,
    UniMessage as UniMessage,
    UniMsg as UniMsg,
    UniTarget as UniTarget,
    uni_image as uni_image,
    uni_text as uni_text,
    uni_video as uni_video,
)

from hoshino.platform.ob11.depends import (
    EventMessage as EventMessage,
    GroupID as GroupID,
    GroupMemberName as GroupMemberName,
    MessageID as MessageID,
    PlainText as PlainText,
    RawMessage as RawMessage,
    ReplyMessage as ReplyMessage,
    SenderID as SenderID,
)
