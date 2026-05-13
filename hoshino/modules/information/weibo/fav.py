import json
import random
import re
from typing import TYPE_CHECKING

from hoshino import Bot, Event, Message, SUPERUSER, data_dir
from hoshino.util import send_segments

from .sv import sv
from .internal.post_runtime import (
    post_msg_from_uid_id,
    render_messages,
    weibo_msg_dir,
)

if TYPE_CHECKING:
    pass


def _load_weibo_favs() -> dict[str, list[str]]:
    fav_json = data_dir / "weibofavorite.json"
    if not fav_json.exists():
        return {}
    try:
        data = json.loads(fav_json.read_text(encoding="utf-8"))
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
    fav_json = data_dir / "weibofavorite.json"
    fav_json.write_text(
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
    uid, id = uid_id.split("_", 1)
    post_message = await post_msg_from_uid_id(uid, id)
    if not post_message:
        await bot.send(event, f"无法还原微博收藏: {uid_id}")
        return
    msgs = render_messages(post_message)
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

    msgs = render_messages(post_message)
    if not msgs:
        await bot.send(event, f"微博收藏为空: {uid_id}")
        return

    await send_segments(msgs)


__all__ = [
    "append_fav",
    "random_weibo_favorite",
    "search_weibo_favorite",
    "show_weibo_favorite",
]
