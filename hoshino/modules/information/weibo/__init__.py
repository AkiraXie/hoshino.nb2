# Thanks to https://github.com/MountainDash/nonebot-bison

import asyncio
from datetime import datetime
import json
import random
import time
from hoshino import Bot, Event, Message, SUPERUSER,data_dir
from hoshino.permission import ADMIN
from nonebot.typing import T_State
from hoshino.util import (
    send_segments,
    send_to_superuser,
    random_image_or_video_by_path,
)
from .db import (
    add_or_update_subscription,
    get_group_config,
    list_group_subscriptions,
    list_group_subscriptions_by_name,
    list_group_subscriptions_by_uid,
    list_subscriptions_by_name,
    list_subscriptions_by_uid,
    remove_group_subscriptions_by_name,
    remove_group_subscriptions_by_uid,
    update_group_config,
)
from .sub import uid_manager
from .utils import (
    sv,
    get_weibo_new,
    post_msg_from_uid_id,
    parse_mapp_weibo,
    parse_weibo_with_id,
    render_post_message,
    get_cached_weibo_uid_id,
    weibo_img_dir,
    weibo_msg_dir,
    weibo_video_dir,
)
import re
from hoshino.event import GroupMsgEmojiLikeEvent
from nonebot.typing import T_State
from nonebot.compat import type_validate_python

weibo_fav_json = data_dir / "weibofavorite.json"


def _load_weibo_favs() -> dict[str, list[str]]:
    if not weibo_fav_json.exists():
        return {}
    try:
        data = json.loads(weibo_fav_json.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}

    favorites: dict[str, list[str]] = {}
    for uid, ids in data.items():
        if not isinstance(uid, str) or not isinstance(ids, list):
            continue
        favorites[uid] = [str(post_id) for post_id in ids if post_id]
    return favorites


def _save_weibo_favs(favorites: dict[str, list[str]]) -> None:
    weibo_fav_json.write_text(
        json.dumps(favorites, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def append_fav(uid: str, id: str) -> bool:
    uid = str(uid)
    id = str(id)
    favorites = _load_weibo_favs()
    ids = favorites.get(uid, [])
    if id in ids:
        return False
    ids.append(id)
    favorites[uid] = ids
    _save_weibo_favs(favorites)
    return True


def _list_favorite_uid_ids(target_uid: str | None = None) -> list[str]:
    favorites = _load_weibo_favs()
    uid_ids: list[str] = []
    for uid, ids in favorites.items():
        if target_uid and uid != target_uid:
            continue
        uid_ids.extend(f"{uid}_{post_id}" for post_id in ids)
    return uid_ids


def _load_favorite_post_metadata(uid: str, post_id: str) -> dict[str, str] | None:
    metadata_path = weibo_msg_dir / uid / post_id / "message.json"
    if not metadata_path.exists():
        return None

    try:
        data = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None

    content = str(data.get("content") or data.get("text") or "").strip()
    if not content:
        return None

    return {
        "uid": str(data.get("uid") or uid),
        "id": str(data.get("id") or post_id),
        "content": content,
    }


def _summarize_favorite_content(content: str, limit: int = 80) -> str:
    content = re.sub(r"\s+", " ", content).strip()
    if len(content) <= limit:
        return content
    return content[: limit - 3] + "\n..."


def _search_favorite_posts(
    keyword: str,
    target_uid: str | None = None,
) -> list[dict[str, str]]:
    keyword = keyword.strip()
    if not keyword:
        return []

    needle = keyword.casefold()
    results: list[dict[str, str]] = []
    seen: set[str] = set()
    for uid_id in _list_favorite_uid_ids(target_uid):
        uid, post_id = uid_id.split("_", 1)
        metadata = _load_favorite_post_metadata(uid, post_id)
        if not metadata:
            continue

        if needle not in metadata["content"].casefold():
            continue

        unique_key = f"{metadata['uid']}_{metadata['id']}"
        if unique_key in seen:
            continue

        seen.add(unique_key)
        results.append(metadata)
    return results


def _resolve_favorite_uid_ids(post_ref: str) -> list[str]:
    post_ref = post_ref.strip()
    if not post_ref:
        return []

    favorites = _load_weibo_favs()
    if "_" in post_ref:
        uid, post_id = post_ref.split("_", 1)
        if post_id in favorites.get(uid, []):
            return [f"{uid}_{post_id}"]
        return []

    matched: list[str] = []
    for uid, ids in favorites.items():
        if post_ref in ids:
            matched.append(f"{uid}_{post_ref}")
    return matched


def _build_favorite_search_messages(
    keyword: str,
    results: list[dict[str, str]],
    target_uid: str | None = None,
) -> list[Message]:
    lines = []
    for item in results:
        summary = _summarize_favorite_content(item["content"])
        lines.append(f"UID: {item['uid']} ID: {item['id']} 内容: {summary}")

    chunks = [lines[index : index + 10] for index in range(0, len(lines), 10)]
    messages: list[Message] = []
    total = len(results)
    scope = f" UID: {target_uid}" if target_uid else ""
    for index, chunk in enumerate(chunks, start=1):
        header = f"微博收藏搜索结果{scope}: 关键词 {keyword}，共 {total} 条，第 {index}/{len(chunks)} 组"
        text = "\n".join([header, *chunk])
        if index == len(chunks):
            text += "\n使用 查看微博收藏 ID"
            text += "\n或 查看微博收藏 UID_ID"
        messages.append(Message(text))
    return messages


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


def format_weibo_config_bits(group_id: int) -> str:
    config = get_group_config(group_id)
    return f"{config.only_pic}{config.send_screenshot}{config.send_segments}"


def format_weibo_config_message(group_id: int, *, editable: bool) -> str:
    bits = format_weibo_config_bits(group_id)
    message = (
        "当前微博推送配置: "
        f"{bits}\n"
        "位序: only_pic send_screenshot send_segments\n"
        "含义: 1=开 0=关"
    )
    if editable:
        message += "\n请发送 3 位二进制配置，例如 011"
    return message


configwb = sv.on_command(
    "configwb",
    aliases=("wbconfig"),
    permission=ADMIN,
)

showconfigwb = sv.on_command(
    "showconfigwb",
    aliases=("wbshowconfig"),
    permission=ADMIN,
)


@configwb.handle()
async def show_weibo_config(bot: Bot, event: Event):
    gid = event.group_id
    await bot.send(event, format_weibo_config_message(gid, editable=True))


@showconfigwb.handle()
async def show_weibo_config_readonly(bot: Bot, event: Event):
    gid = event.group_id
    await showconfigwb.finish(format_weibo_config_message(gid, editable=False))


@configwb.got("config_bits")
async def set_weibo_config(state: T_State, event: Event):
    gid = event.group_id
    config_bits = str(state["config_bits"]).strip()
    if not re.fullmatch(r"[01]{3}", config_bits):
        current_bits = format_weibo_config_bits(gid)
        await configwb.reject(
            "输入格式错误，请发送 3 位二进制，例如 011\n"
            f"当前配置仍为: {current_bits}\n"
            "位序: only_pic send_screenshot send_segments"
        )

    only_pic, send_screenshot, send_segments = (int(bit) for bit in config_bits)
    update_group_config(
        gid,
        only_pic=only_pic,
        send_screenshot=send_screenshot,
        send_segments=send_segments,
    )
    await configwb.finish(
        "微博推送配置已更新: "
        f"{config_bits}\n"
        f"only_pic={only_pic}, send_screenshot={send_screenshot}, send_segments={send_segments}"
    )


@sv.on_command(
    "微博随图",
    aliases=("wbimg", "wim"),
    only_group=False,
    only_to_me=True,
    permission=SUPERUSER,
    priority=5,
)
async def weibo_random_image(event: Event):
    path = weibo_img_dir
    num = 12
    text = event.get_plaintext().strip()
    texts = text.split(maxsplit=1)
    keyword = None
    if len(texts) == 2:
        keyword, num_str = texts
        if num_str.isdigit():
            num = int(num_str)
        else:
            keyword = keyword + num_str
    elif len(texts) == 1:
        keyword = texts[0]
        if keyword.isdigit():
            num = int(keyword)
    seed = time.time() + event.message_id
    imgs = random_image_or_video_by_path(
        path, num=num, seed=seed, video=False, keyword=keyword
    )
    await send_segments(imgs)


@sv.on_command(
    "微博随影",
    aliases=("wbvid", "wvi"),
    only_to_me=True,
    only_group=False,
    permission=SUPERUSER,
    priority=5,
)
async def weibo_random_video(event: Event):
    path = weibo_video_dir
    num = 2
    text = event.get_plaintext().strip()
    texts = text.split(maxsplit=1)
    keyword = None
    if len(texts) == 2:
        keyword, num_str = texts
        if num_str.isdigit():
            num = int(num_str)
        else:
            keyword = keyword + num_str
    elif len(texts) == 1:
        keyword = texts[0]
        if keyword.isdigit():
            num = int(keyword)
    seed = time.time() + event.message_id
    imgs = random_image_or_video_by_path(
        path, num=num, seed=seed, video=True, keyword=keyword
    )
    await send_segments(imgs)


@sv.on_command(
    "随机微博收藏",
    aliases=("微博随机收藏", "收藏微博", "randwbfav", "rwbfav"),
    only_group=False,
    only_to_me=True,
    permission=SUPERUSER,
    priority=5,
)
async def random_weibo_favorite(bot: Bot, event: Event):
    target_uid = event.get_plaintext().strip() or None
    uid_ids = _list_favorite_uid_ids(target_uid)
    if not uid_ids:
        if target_uid:
            await bot.send(event, f"没有找到 UID {target_uid} 的微博收藏")
        else:
            await bot.send(event, "当前没有微博收藏")
        return
    uid_id = random.choice(uid_ids)
    uid,id = uid_id.split("_", 1)
    post_message = await post_msg_from_uid_id(uid,id)
    if not post_message:
        await bot.send(event, f"无法还原微博收藏: {uid_id}")
        return
    msgs = render_post_message(post_message)
    if not msgs:
        await bot.send(event, f"微博收藏为空: {uid_id}")
        return
    await send_segments(msgs)


@sv.on_command(
    "搜索微博收藏",
    aliases=("搜微博收藏", "微博收藏搜索", "wbfavsearch", "searchwbfav"),
    only_group=False,
    permission=SUPERUSER,
    priority=5,
)
async def search_weibo_favorite(bot: Bot, event: Event):
    arg = event.get_plaintext().strip()
    if not arg:
        await bot.send(event, "用法: 搜索微博收藏 关键词\n或: 搜索微博收藏 UID 关键词")
        return

    target_uid = None
    keyword = arg
    parts = arg.split(maxsplit=1)
    if len(parts) == 2 and parts[0].isdecimal():
        target_uid, keyword = parts

    results = _search_favorite_posts(keyword, target_uid=target_uid)
    if not results:
        if target_uid:
            await bot.send(event, f"没有找到 UID {target_uid} 中包含 {keyword} 的微博收藏")
        else:
            await bot.send(event, f"没有找到包含 {keyword} 的微博收藏")
        return

    messages = _build_favorite_search_messages(keyword, results, target_uid=target_uid)
    await send_segments(messages)


@sv.on_command(
    "查看微博收藏",
    aliases=("重现微博收藏", "显示微博收藏", "showwbfav", "getwbfav"),
    only_group=False,
    permission=SUPERUSER,
    priority=5,
)
async def show_weibo_favorite(bot: Bot, event: Event):
    post_ref = event.get_plaintext().strip()
    if not post_ref:
        await bot.send(event, "用法: 查看微博收藏 ID\n或: 查看微博收藏 UID_ID")
        return

    matched = _resolve_favorite_uid_ids(post_ref)
    if not matched:
        await bot.send(event, f"没有找到微博收藏: {post_ref}")
        return

    if len(matched) > 1:
        lines = ["找到多个同名收藏，请改用 UID_ID:", *matched[:10]]
        if len(matched) > 10:
            lines.append(f"还有 {len(matched) - 10} 条未展示")
        await bot.send(event, "\n".join(lines))
        return

    uid_id = matched[0]
    uid, post_id = uid_id.split("_", 1)
    post_message = await post_msg_from_uid_id(uid, post_id)
    if not post_message:
        await bot.send(event, f"无法还原微博收藏: {uid_id}")
        return

    msgs = render_post_message(post_message)
    if not msgs:
        await bot.send(event, f"微博收藏为空: {uid_id}")
        return

    await send_segments(msgs)


@sv.on_command(
    "添加微博订阅",
    aliases=("订阅微博", "新增微博", "添加微博", "添加weibo", "addweibo", "addwb"),
)
async def add_subscription(bot: Bot, event: Event):
    gid = event.group_id
    msg = event.get_plaintext().strip()
    keywords = []
    try:
        msg = msg.split(" ")
        if len(msg) == 1:
            uid = msg[0]
        else:
            uid = msg[0]
            keywords = msg[1:]
        if not uid.isdecimal():
            match = re.search(r"weibo\.com\/(u\/)?(\d+)", uid)
            if match:
                uid = match.group(2)
            else:
                await bot.send(
                    event, "无效的UID格式，请输入数字ID或完整的微博个人主页链接"
                )
                return
        post = await get_weibo_new(uid, ts=0)
        if not post:
            await bot.send(event, f"无法获取微博用户信息，UID: {uid}")
            return
    except Exception as e:
        sv.logger.exception(e)
        await bot.send(event, f"无法获取微博用户信息，UID: {uid}")
        return
    kw = "-_-".join(keywords) if keywords else ""
    ts = time.time()
    add_or_update_subscription(gid, uid, post.nickname, ts, kw)
    await uid_manager.add_uid(uid)
    if keywords:
        await bot.send(
            event, f"成功订阅微博用户：{post.nickname} UID: {uid} 关键词: {kw}"
        )
    else:
        await bot.send(event, f"成功订阅微博用户：{post.nickname} UID: {uid}")


@sv.on_command(
    "删除微博订阅", aliases=("取消微博", "删除微博", "rmweibo", "删除weibo", "rmwb")
)
async def remove_subscription(bot: Bot, event: Event):
    gid = event.group_id
    uids = event.get_plaintext().strip()
    uids = uids.split()
    for uid in uids:
        await asyncio.sleep(0.3)
        if uid.isdecimal():
            num = remove_group_subscriptions_by_uid(gid, uid)
            if num:
                await uid_manager.remove_uid(
                    uid, lambda u: bool(list_subscriptions_by_uid(u))
                )
        else:
            num, target_uid = remove_group_subscriptions_by_name(gid, uid)
            if num and target_uid:
                await uid_manager.remove_uid(
                    target_uid,
                    lambda u: bool(list_subscriptions_by_uid(u)),
                )
        if num:
            await bot.send(event, f"{uid} 删除微博订阅成功")
        else:
            await bot.send(event, f"{uid} 删除微博订阅失败")


@sv.on_command("微博订阅", aliases=("微博订阅列表", "lookweibo", "lswb", "listweibo"))
async def list_subscriptions(bot: Bot, event: Event):
    gid = event.group_id
    rows = list_group_subscriptions(gid)
    if not rows:
        await bot.send(event, "本群没有订阅微博用户")
        return
    msg = "当前订阅的微博用户：\n"
    for i, row in enumerate(rows):
        uid = row.uid
        name = row.name
        ts = datetime.fromtimestamp(row.time).strftime("%Y-%m-%d %H:%M:%S")
        msg += f"{i + 1}. UID: {uid}, 昵称: {name}, 上次更新时间: {ts}\n"
    await bot.send(event, msg)


@sv.on_command("微博最新订阅", aliases=("查看微博最新", "seeweibo", "kkwb", "seewb"))
async def see_weibo(bot: Bot, event: Event):
    gid = event.group_id
    arg = event.get_plaintext().strip()
    if arg.isdecimal():
        rows = list_group_subscriptions_by_uid(gid, arg)
    else:
        rows = list_group_subscriptions_by_name(gid, arg)
    if not rows:
        await bot.send(event, f"没有订阅{arg}微博")
    else:
        uid = rows[0].uid
        keywords = rows[0].keyword
        if keywords:
            keywords = keywords.split("-_-")
        else:
            keywords = []
        post = await get_weibo_new(uid, 0)
        if not post:
            await bot.send(event, f"没有获取到{arg}微博")
            return
        post_message = await post.get_message(full=True)
        msgs = post.render_message(post_message)
        await send_segments(msgs)


@sv.on_command(
    "查库微博",
    aliases=("wbquery", "微博查库"),
    permission=SUPERUSER,
    only_group=False,
    only_to_me=True,
)
async def query_weibo_user(bot: Bot, event: Event):
    arg = event.get_plaintext().strip()
    if arg.isdecimal():
        rows = list_subscriptions_by_uid(arg)
    else:
        rows = list_subscriptions_by_name(arg)
    if not rows:
        await bot.send(event, f"没有查到微博用户 {arg}")
        return
    msg = "微博用户信息:\n"
    for row in rows:
        msg += (
            f"UID: {row.uid}, 昵称: {row.name}, 关键词: {row.keyword or '无'}, "
            f"上次更新时间: {datetime.fromtimestamp(row.time).strftime('%Y-%m-%d %H:%M:%S')}\n"
        )
        break
    await bot.send(event, msg)
