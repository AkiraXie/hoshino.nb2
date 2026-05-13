import re

from hoshino import Bot, SUPERUSER
from hoshino.event import GroupMsgEmojiLikeEvent
from hoshino.util import send_to_superuser
from nonebot.typing import T_State
from nonebot.compat import type_validate_python
from hoshino import Message

from .sv import sv
from .internal.post_runtime import get_cached_weibo_uid_id
from .fav import append_fav


weibo_regexs = {
    "weibo": re.compile(r"(http:|https:)\/\/weibo\.com\/(\d+)\/(\w+)"),
    "mweibo": re.compile(r"(http:|https:)\/\/m\.weibo\.cn\/(detail|status)\/(\w+)"),
    "mappweibo": re.compile(r"(http:|https:)\/\/mapp\.api\.weibo\.cn\/fx\/(\w+)\.html"),
}


async def reaction_weibo_rule(
    bot: Bot,
    event: GroupMsgEmojiLikeEvent,
    state: T_State,
) -> bool:
    if event.get_emoji() != "319":
        return False
    msg_id = event.message_id
    msg = await bot.get_msg(message_id=msg_id)
    sender = msg.get("sender", {}).get("user_id")
    sender = str(sender)
    if sender != bot.self_id and sender not in bot.config.superusers:
        return False
    msg = msg.get("message")
    if msg:
        msg = type_validate_python(Message, msg)
        text = msg.extract_plain_text()
        text = text.strip()
        for name, regex in weibo_regexs.items():
            matched = regex.search(text)
            if matched:
                state["__weibo_name"] = name
                state["__weibo_url"] = matched.group(0)
                state["__weibo_matched"] = matched
                state["__weibo_msg_id"] = msg_id
                sv.logger.info(f"Matched weibo URL in reaction: {state['__weibo_url']}")
                return True
    return False


svpost_notice = sv.on_notice(
    rule=reaction_weibo_rule,
    permission=SUPERUSER,
    priority=5,
    block=True,
)


@svpost_notice.handle()
async def handle_weibo_reaction(state: T_State):
    if not (name := state.get("__weibo_name")):
        return
    if not (matched := state.get("__weibo_matched")):
        return
    if not (url := state.get("__weibo_url")):
        return
    if not (msg_id := state.get("__weibo_msg_id")):
        return
    if cached := get_cached_weibo_uid_id(msg_id):
        uid, id = cached.split("_", 1)
        appended = append_fav(uid, id)
        if appended:
            sv.logger.info(f"Added weibo to fav by cache: {uid} {id}")
            await send_to_superuser(f"微博收藏新增: UID {uid} ID {id} URL {url} (from cache)")

    else:
        try:
            from .request import parse_weibo_with_id, parse_mapp_weibo

            if name == "weibo":
                _, _, post_id = matched.groups()
                post = await parse_weibo_with_id(post_id)
            elif name == "mweibo":
                _, _, post_id = matched.groups()
                post = await parse_weibo_with_id(post_id)
            elif name == "mappweibo":
                post = await parse_mapp_weibo(url)
            else:
                sv.logger.error(f"Unknown weibo type: {name}")
                return
            if post:
                appended = append_fav(post.uid, post.id)
                if appended:
                    sv.logger.info(f"Added weibo to fav: {post.uid} {post.id}")
                    await send_to_superuser(f"微博收藏新增: UID {post.uid} ID {post.id} URL {post.url}")
            else:
                sv.logger.error(f"Failed to parse weibo URL: {url}")
        except Exception as e:
            sv.logger.error(f"Error handling weibo reaction: {e} url: {url}")


__all__ = [
    "weibo_regexs",
    "reaction_weibo_rule",
    "handle_weibo_reaction",
]
