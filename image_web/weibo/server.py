"""Weibo Image Web provider —— 微博瀑布流图片浏览站点（奶油风）。

数据源为 ``data/weibomsgs/`` 目录树（``uid/post_id/message.json`` + images/videos），
索引支持增量刷新与磁盘缓存。额外提供 tags、blacklist、删除（移入回收站）等能力。
前端位于 ``weibo_image_web/frontend``。
"""

import asyncio
import contextlib
import json
import logging
import os
import re
import shutil
import threading
from collections import Counter
from collections.abc import Coroutine
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from PIL import Image
from pydantic import BaseModel

from image_web.common.auth import require_write_token
from image_web.common.env import read_env_data_dir
from image_web.common.favorites import FavoritesStore, register_favorite_mutations
from image_web.common.jsonstore import load_json, save_json
from image_web.common.lifecycle import build_lifespan
from image_web.common.middleware import add_cache_headers_middleware, setup_cors
from image_web.common.pagination import paginate
from image_web.common.spa import mount_frontend

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent.parent

DATA_DIR = read_env_data_dir(PROJECT_ROOT)
WEIBO_MSG_DIR = DATA_DIR / "weibomsgs"
THUMB_DIR = DATA_DIR / "thumbnails"
TRASH_DIR = DATA_DIR / "weibomsgs_trash"
FAV_JSON = DATA_DIR / "weibofavorite.json"
TAGS_JSON = DATA_DIR / "weibotags.json"
BLACKLIST_JSON = DATA_DIR / "weiboblacklist.json"
INDEX_CACHE = DATA_DIR / "index_cache.json"
FRONTEND_DIST = PROJECT_ROOT / "weibo_image_web" / "frontend" / "dist"

AUTO_REFRESH_INTERVAL = 30 * 60  # seconds

posts_index: list[dict] = []
uid_nickname_map: dict[str, str] = {}
# {uid}_{post_id} -> 帖子内容指纹（message.json mtime + 媒体文件名列表），增量刷新用
_post_fingerprints: dict[str, str] = {}
_build_lock = threading.RLock()
_tags_lock = asyncio.Lock()
_blacklist_lock = asyncio.Lock()
# 持有 fire-and-forget 后台任务引用，防止任务被 GC 中途取消（RUF006）
_background_tasks: set[asyncio.Task[Any]] = set()

_fav_store = FavoritesStore(FAV_JSON)


# ── helpers ──────────────────────────────────────────────


def _num_sort_key(p: Path) -> int:
    m = re.match(r"(\d+)", p.stem)
    return int(m.group(1)) if m else 0


def _extract_nickname(text: str) -> str:
    if not text:
        return ""
    m = re.match(r"^(.+?)\s*微博~", text)
    return m.group(1).strip() if m else ""


def _generate_thumbnails(uid: str, post_id: str, source_path: Path) -> bool:
    """Generate cover thumbnails (JPEG + WebP) at 600px wide."""
    thumb_dir = THUMB_DIR / uid / post_id
    thumb_dir.mkdir(parents=True, exist_ok=True)
    jpg_dest = thumb_dir / "cover.jpg"
    webp_dest = thumb_dir / "cover.webp"
    if jpg_dest.exists() and webp_dest.exists():
        return True
    try:
        img = Image.open(source_path)
        img.thumbnail((600, 800))
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        img.save(jpg_dest, "JPEG", quality=82, optimize=True)
        img.save(webp_dest, "WEBP", quality=82, optimize=True)
        return True
    except Exception:
        logger.exception(
            "failed to generate thumbnails for %s/%s from %s", uid, post_id, source_path
        )
        return False


def _load_blacklist() -> list[str]:
    """Load blacklisted UIDs."""
    data = load_json(BLACKLIST_JSON, [])
    if not isinstance(data, list):
        return []
    return [str(uid) for uid in data]


def _save_blacklist(uids: list[str]) -> None:
    save_json(BLACKLIST_JSON, uids)


def _load_tags() -> dict[str, dict[str, list[str]]]:
    """Load tags: {tag_name: {uid: [post_ids]}}"""
    data = load_json(TAGS_JSON, {})
    if not isinstance(data, dict):
        return {}
    return data


def _save_tags(tags: dict[str, dict[str, list[str]]]) -> None:
    save_json(TAGS_JSON, tags)


def _scan_post(uid: str, post_dir: Path) -> dict:
    """Scan a single post directory and return its index entry."""
    post_id = post_dir.name
    meta_path = post_dir / "message.json"
    meta: dict = {}
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            logger.warning("failed to read %s; using defaults", meta_path)

    images_dir = post_dir / "images"
    image_count = len(list(images_dir.glob("*.jpg"))) if images_dir.is_dir() else 0
    videos_dir = post_dir / "videos"
    video_count = len(list(videos_dir.glob("*.mp4"))) if videos_dir.is_dir() else 0

    text = str(meta.get("text") or "")
    content = str(meta.get("content") or "")
    nickname = str(meta.get("nickname") or "") or _extract_nickname(text)
    timestamp = meta.get("timestamp") or 0
    if not timestamp and meta_path.exists():
        timestamp = os.path.getmtime(str(meta_path))
    url = str(meta.get("url") or "") or f"https://weibo.com/{uid}/{post_id}"
    has_screenshot = (post_dir / "screenshot.jpg").exists()

    cover = None
    if image_count > 0:
        imgs = sorted(images_dir.glob("*.jpg"), key=_num_sort_key)
        if imgs:
            _generate_thumbnails(uid, post_id, imgs[0])
            cover = f"/media/thumbnails/{uid}/{post_id}/cover"
    elif has_screenshot:
        cover = f"/media/{uid}/{post_id}/screenshot.jpg"

    return {
        "uid": uid,
        "id": post_id,
        "content": content,
        "nickname": nickname,
        "timestamp": timestamp,
        "url": url,
        "image_count": image_count,
        "video_count": video_count,
        "has_screenshot": has_screenshot,
        "cover": cover,
    }


def _post_fingerprint(post_dir: Path) -> str:
    """帖子内容指纹：message.json 的 mtime + 媒体文件名列表。

    帖子目录/uid 目录的 mtime 在“原地编辑 message.json”时不会变化，仅按目录 mtime
    判变更会漏掉内容更新；这里改用文件级 mtime 与文件名列表，能发现内容编辑以及
    媒体的增删改名，且不读取文件内容（对每次请求的增量刷新足够廉价）。
    """
    parts: list[str] = []
    meta_path = post_dir / "message.json"
    try:
        parts.append(f"meta:{meta_path.stat().st_mtime_ns}")
    except OSError:
        parts.append("meta:missing")
    for sub in ("images", "videos"):
        sub_dir = post_dir / sub
        names: list[str] = []
        if sub_dir.is_dir():
            # 目录不可读时按空列表计入指纹（下次刷新会重试）。
            with contextlib.suppress(OSError):
                names = sorted(p.name for p in sub_dir.iterdir())
        parts.append(f"{sub}:[{','.join(names)}]")
    parts.append("shot:1" if (post_dir / "screenshot.jpg").exists() else "shot:0")
    return "|".join(parts)


def _load_index_cache() -> tuple[list[dict], dict[str, str]] | None:
    """从磁盘加载索引缓存。返回 (entries, post_fingerprints) 或 None。"""
    if not INDEX_CACHE.exists():
        return None
    try:
        data = json.loads(INDEX_CACHE.read_text(encoding="utf-8"))
        entries = data["entries"]
        p_fps = data.get("post_fingerprints")
        if p_fps is None:
            # 旧格式缓存（post_mtimes 语义）：指纹缺失，下次增量会全量重扫修正。
            p_fps = {}
        return entries, p_fps
    except (OSError, json.JSONDecodeError, KeyError):
        logger.warning("index cache %s is unreadable; will rebuild", INDEX_CACHE)
        return None


def _save_index_cache() -> None:
    """Persist current index to disk for fast startup（原子写）。"""
    data = {
        "entries": posts_index,
        "post_fingerprints": _post_fingerprints,
    }
    save_json(INDEX_CACHE, data)


def _build_index_full() -> None:
    """Full rebuild — scan everything from scratch."""
    global posts_index, uid_nickname_map, _post_fingerprints

    with _build_lock:
        index: list[dict] = []
        umap: dict[str, str] = {}
        p_fps: dict[str, str] = {}

        if not WEIBO_MSG_DIR.is_dir():
            posts_index, uid_nickname_map = [], {}
            _post_fingerprints = {}
            return

        for uid_dir in WEIBO_MSG_DIR.iterdir():
            if not uid_dir.is_dir():
                continue
            uid = uid_dir.name
            for post_dir in uid_dir.iterdir():
                if not post_dir.is_dir():
                    continue
                p_fps[f"{uid}_{post_dir.name}"] = _post_fingerprint(post_dir)
                entry = _scan_post(uid, post_dir)
                if entry["nickname"]:
                    umap.setdefault(uid, entry["nickname"])
                index.append(entry)

        index.sort(key=lambda e: e.get("timestamp") or 0, reverse=True)
        posts_index = index
        uid_nickname_map = umap
        _post_fingerprints = p_fps
        _save_index_cache()


def _build_index_incremental() -> int:
    """增量刷新：全量比对帖子内容指纹，仅重扫指纹变化的帖子。

    Returns the number of posts added/updated/removed.
    """
    global posts_index, uid_nickname_map, _post_fingerprints

    if not WEIBO_MSG_DIR.is_dir():
        if posts_index:
            posts_index, uid_nickname_map = [], {}
            _post_fingerprints = {}
            _save_index_cache()
        return 0

    changes = 0

    # 1. 采集磁盘上所有帖子的内容指纹
    current_fps: dict[str, str] = {}
    for uid_dir in WEIBO_MSG_DIR.iterdir():
        if not uid_dir.is_dir():
            continue
        uid = uid_dir.name
        for post_dir in uid_dir.iterdir():
            if not post_dir.is_dir():
                continue
            current_fps[f"{uid}_{post_dir.name}"] = _post_fingerprint(post_dir)

    # 2. 已删除的帖子
    removed_keys = set(_post_fingerprints) - set(current_fps)
    if removed_keys:
        posts_index = [p for p in posts_index if f"{p['uid']}_{p['id']}" not in removed_keys]
        for key in removed_keys:
            _post_fingerprints.pop(key, None)
        uid_nickname_map = {
            uid: nick
            for uid, nick in uid_nickname_map.items()
            if any(k.startswith(f"{uid}_") for k in _post_fingerprints)
        }
        changes += len(removed_keys)

    # 3. 新增或内容变化的帖子（原地编辑 message.json 也会被发现）
    for key, fingerprint in current_fps.items():
        if _post_fingerprints.get(key) == fingerprint:
            continue
        uid, post_id = key.split("_", 1)
        entry = _scan_post(uid, WEIBO_MSG_DIR / uid / post_id)
        _post_fingerprints[key] = fingerprint

        if entry["nickname"]:
            uid_nickname_map.setdefault(uid, entry["nickname"])

        for i, post in enumerate(posts_index):
            if post["uid"] == uid and post["id"] == post_id:
                posts_index[i] = entry  # Updated — replace in-place
                break
        else:
            posts_index.append(entry)  # New post
        changes += 1

    if changes:
        posts_index.sort(key=lambda e: e.get("timestamp") or 0, reverse=True)
        _save_index_cache()

    return changes


def _build_index() -> None:
    """Smart index build: load cache on first call, then incremental."""
    global posts_index, uid_nickname_map, _post_fingerprints

    with _build_lock:
        if not posts_index:
            cached = _load_index_cache()
            if cached is not None:
                entries, p_fps = cached
                posts_index = entries
                _post_fingerprints = p_fps
                umap: dict[str, str] = {}
                for e in entries:
                    if e.get("nickname"):
                        umap.setdefault(e["uid"], e["nickname"])
                uid_nickname_map = umap
                _build_index_incremental()
                return
            _build_index_full()
        else:
            _build_index_incremental()


def _generate_all_missing_thumbnails() -> int:
    """Generate missing thumbnails for all indexed posts. Returns count of generated."""
    generated = 0
    for entry in posts_index:
        uid = entry["uid"]
        post_id = entry["id"]
        thumb_dir = THUMB_DIR / uid / post_id
        if (thumb_dir / "cover.jpg").exists() and (thumb_dir / "cover.webp").exists():
            continue
        images_dir = WEIBO_MSG_DIR / uid / post_id / "images"
        if images_dir.is_dir():
            imgs = sorted(images_dir.glob("*.jpg"), key=_num_sort_key)
            if imgs and _generate_thumbnails(uid, post_id, imgs[0]):
                generated += 1
    return generated


def _spawn(coro: Coroutine[Any, Any, Any]) -> asyncio.Task[Any]:
    """Fire-and-forget 后台任务：持有引用防 GC 中途取消，异常记录日志。"""
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_on_task_done)
    return task


def _on_task_done(task: asyncio.Task[Any]) -> None:
    _background_tasks.discard(task)
    if task.cancelled():
        return
    if (exc := task.exception()) is not None:
        logger.error("background task %s failed", task.get_name(), exc_info=exc)


async def _startup_thumbnails() -> None:
    _spawn(asyncio.to_thread(_generate_all_missing_thumbnails))


# ── models ───────────────────────────────────────────────


class TagBody(BaseModel):
    uid: str
    id: str
    tag: str


class BlacklistBody(BaseModel):
    uid: str


# ── API routes ───────────────────────────────────────────

router = APIRouter()


@router.get("/api/posts")
async def api_list_posts(page: int = 1, size: int = 20, uid: str = "", q: str = "", date: str = ""):
    await asyncio.to_thread(_build_index)
    blacklist = set(_load_blacklist())
    results = [p for p in posts_index if p["uid"] not in blacklist]
    if uid:
        results = [p for p in results if p["uid"] == uid]
    if q:
        needle = q.lower()
        results = [
            p
            for p in results
            if needle in (p.get("content") or "").lower()
            or needle in (p.get("nickname") or "").lower()
        ]
    if date in ("today", "yesterday", "older"):
        tz = timezone(timedelta(hours=8))
        now = datetime.now(tz)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        if date == "today":
            ts_min = today_start.timestamp()
            ts_max = float("inf")
        elif date == "yesterday":
            ts_min = (today_start - timedelta(days=1)).timestamp()
            ts_max = today_start.timestamp()
        else:  # older
            ts_min = 0
            ts_max = (today_start - timedelta(days=1)).timestamp()
        results = [p for p in results if ts_min <= (p.get("timestamp") or 0) < ts_max]
    total, page_items = paginate(results, page, size)
    return {
        "total": total,
        "page": page,
        "size": size,
        "items": page_items,
    }


@router.get("/api/posts/{uid}/{post_id}")
async def api_get_post(uid: str, post_id: str):
    entry = next((p for p in posts_index if p["uid"] == uid and p["id"] == post_id), None)
    if not entry:
        raise HTTPException(404, "Post not found")

    post_dir = WEIBO_MSG_DIR / uid / post_id
    images_dir = post_dir / "images"
    images = (
        [
            f"/media/{uid}/{post_id}/images/{f.name}"
            for f in sorted(images_dir.glob("*.jpg"), key=_num_sort_key)
        ]
        if images_dir.is_dir()
        else []
    )
    videos_dir = post_dir / "videos"
    videos = (
        [
            f"/media/{uid}/{post_id}/videos/{f.name}"
            for f in sorted(videos_dir.glob("*.mp4"), key=_num_sort_key)
        ]
        if videos_dir.is_dir()
        else []
    )
    screenshot = f"/media/{uid}/{post_id}/screenshot.jpg" if entry["has_screenshot"] else None
    return {**entry, "images": images, "videos": videos, "screenshot": screenshot}


@router.get("/api/uids")
async def api_list_uids():
    blacklist = set(_load_blacklist())
    return {uid: nick for uid, nick in uid_nickname_map.items() if uid not in blacklist}


@router.get("/api/uid-stats")
async def api_uid_stats():
    """Per-uid statistics: total images, favorited post count."""
    favs = _fav_store.load()
    blacklist = set(_load_blacklist())
    stats: dict[str, dict] = {}
    for entry in posts_index:
        if entry["uid"] in blacklist:
            continue
        uid = entry["uid"]
        if uid not in stats:
            stats[uid] = {"image_count": 0, "fav_count": 0}
        stats[uid]["image_count"] += entry.get("image_count", 0)
    for uid, ids in favs.items():
        if uid in stats:
            stats[uid]["fav_count"] = len(ids)
        else:
            stats[uid] = {"image_count": 0, "fav_count": len(ids)}
    return stats


@router.get("/api/stats/top-uids")
async def api_top_uids(limit: int = 5, preview: int = 4, date: str = ""):
    """Top N most active UIDs with preview posts."""
    blacklist = set(_load_blacklist())
    source = [p for p in posts_index if p["uid"] not in blacklist]
    if date in ("today", "yesterday", "older"):
        tz = timezone(timedelta(hours=8))
        now = datetime.now(tz)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        if date == "today":
            ts_min, ts_max = today_start.timestamp(), float("inf")
        elif date == "yesterday":
            ts_min = (today_start - timedelta(days=1)).timestamp()
            ts_max = today_start.timestamp()
        else:
            ts_min, ts_max = 0, (today_start - timedelta(days=1)).timestamp()
        source = [p for p in source if ts_min <= (p.get("timestamp") or 0) < ts_max]

    uid_counts = Counter(p["uid"] for p in source)
    top = uid_counts.most_common(limit)
    result = []
    for uid, count in top:
        posts = [p for p in source if p["uid"] == uid][:preview]
        result.append(
            {
                "uid": uid,
                "nickname": uid_nickname_map.get(uid, uid),
                "count": count,
                "posts": posts,
            }
        )
    return result


# ── Favorites (读取接口；写入接口由 common 注册) ──────────


@router.get("/api/favorites")
async def api_list_favorites(page: int = 1, size: int = 20):
    favs = _fav_store.load()
    blacklist = set(_load_blacklist())
    fav_set = {f"{uid}_{pid}" for uid, ids in favs.items() for pid in ids}
    fav_posts = [
        p for p in posts_index if f"{p['uid']}_{p['id']}" in fav_set and p["uid"] not in blacklist
    ]
    total, page_items = paginate(fav_posts, page, size)
    return {
        "total": total,
        "page": page,
        "size": size,
        "items": page_items,
    }


@router.get("/api/favorites/ids")
async def api_favorite_ids():
    favs = _fav_store.load()
    blacklist = set(_load_blacklist())
    return [f"{uid}_{pid}" for uid, ids in favs.items() if uid not in blacklist for pid in ids]


# ── Blacklist API ────────────────────────────────────────


@router.get("/api/blacklist")
async def api_list_blacklist():
    """Return blacklisted UIDs with nicknames."""
    uids = _load_blacklist()
    return [{"uid": uid, "nickname": uid_nickname_map.get(uid, uid)} for uid in uids]


@router.post("/api/blacklist", dependencies=[Depends(require_write_token)])
async def api_add_blacklist(body: BlacklistBody):
    async with _blacklist_lock:
        bl = _load_blacklist()
        if body.uid not in bl:
            bl.append(body.uid)
            _save_blacklist(bl)
    return {"ok": True}


@router.delete("/api/blacklist/{uid}", dependencies=[Depends(require_write_token)])
async def api_remove_blacklist(uid: str):
    async with _blacklist_lock:
        bl = _load_blacklist()
        if uid not in bl:
            raise HTTPException(404, "Not in blacklist")
        bl.remove(uid)
        _save_blacklist(bl)
    return {"ok": True}


# ── Tags API ─────────────────────────────────────────────


@router.get("/api/tags")
async def api_list_tags():
    """Return all tags with post counts."""
    tags = _load_tags()
    result = []
    for tag_name, uid_map in tags.items():
        count = sum(len(ids) for ids in uid_map.values())
        result.append({"tag": tag_name, "count": count})
    result.sort(key=lambda t: t["count"], reverse=True)
    return result


@router.get("/api/tags/post-map")
async def api_tags_post_map():
    """Return mapping: {uid_postid: [tag1, tag2, ...]} for all tagged posts."""
    tags = _load_tags()
    result: dict[str, list[str]] = {}
    for tag_name, uid_map in tags.items():
        for uid, ids in uid_map.items():
            for pid in ids:
                key = f"{uid}_{pid}"
                result.setdefault(key, []).append(tag_name)
    return result


@router.get("/api/tags/{tag}")
async def api_tag_posts(tag: str, page: int = 1, size: int = 20):
    """Return posts for a specific tag, paginated."""
    tags = _load_tags()
    uid_map = tags.get(tag, {})
    tag_set = {f"{uid}_{pid}" for uid, ids in uid_map.items() for pid in ids}
    blacklist = set(_load_blacklist())
    tag_posts = [
        p for p in posts_index if f"{p['uid']}_{p['id']}" in tag_set and p["uid"] not in blacklist
    ]
    total, page_items = paginate(tag_posts, page, size)
    return {
        "total": total,
        "page": page,
        "size": size,
        "items": page_items,
    }


@router.get("/api/posts/{uid}/{post_id}/tags")
async def api_post_tags(uid: str, post_id: str):
    """Return tags for a specific post."""
    tags = _load_tags()
    result = []
    for tag_name, uid_map in tags.items():
        ids = uid_map.get(uid, [])
        if post_id in ids:
            result.append(tag_name)
    return result


@router.post("/api/tags", dependencies=[Depends(require_write_token)])
async def api_add_tag(body: TagBody):
    """Add a tag to a post."""
    tag = body.tag.strip()
    if not tag:
        raise HTTPException(400, "Tag cannot be empty")
    async with _tags_lock:
        tags = _load_tags()
        uid_map = tags.setdefault(tag, {})
        ids = uid_map.get(body.uid, [])
        if body.id not in ids:
            ids.append(body.id)
            uid_map[body.uid] = ids
        _save_tags(tags)
    return {"ok": True}


@router.delete(
    "/api/tags/{tag}/{uid}/{post_id}",
    dependencies=[Depends(require_write_token)],
)
async def api_remove_tag(tag: str, uid: str, post_id: str):
    """Remove a tag from a post."""
    async with _tags_lock:
        tags = _load_tags()
        uid_map = tags.get(tag, {})
        ids = uid_map.get(uid, [])
        if post_id not in ids:
            raise HTTPException(404, "Tag not found on post")
        ids.remove(post_id)
        if ids:
            uid_map[uid] = ids
        else:
            uid_map.pop(uid, None)
        if uid_map:
            tags[tag] = uid_map
        else:
            tags.pop(tag, None)
        _save_tags(tags)
    return {"ok": True}


@router.delete("/api/tags/{tag}", dependencies=[Depends(require_write_token)])
async def api_delete_tag(tag: str):
    """Delete an entire tag."""
    async with _tags_lock:
        tags = _load_tags()
        if tag not in tags:
            raise HTTPException(404, "Tag not found")
        tags.pop(tag)
        _save_tags(tags)
    return {"ok": True}


@router.delete("/api/posts/{uid}/{post_id}", dependencies=[Depends(require_write_token)])
async def api_delete_post(uid: str, post_id: str):
    """Move a post directory to trash and remove from index / favorites."""
    if not re.fullmatch(r"[\w]+", uid) or not re.fullmatch(r"[\w]+", post_id):
        raise HTTPException(400, "Invalid uid or post_id")

    post_dir = (WEIBO_MSG_DIR / uid / post_id).resolve()
    if not str(post_dir).startswith(str(WEIBO_MSG_DIR.resolve())):
        raise HTTPException(400, "Invalid path")
    if not post_dir.is_dir():
        raise HTTPException(404, "Post not found")

    # Move to trash (reversible) — blocking I/O in thread
    trash_uid_dir = TRASH_DIR / uid
    trash_uid_dir.mkdir(parents=True, exist_ok=True)
    dest = trash_uid_dir / post_id
    if dest.exists():
        await asyncio.to_thread(shutil.rmtree, dest)
    await asyncio.to_thread(shutil.move, str(post_dir), str(dest))

    # Remove from in-memory index and fingerprint cache
    global posts_index
    posts_index = [p for p in posts_index if not (p["uid"] == uid and p["id"] == post_id)]
    _post_fingerprints.pop(f"{uid}_{post_id}", None)

    # Remove from favorites if present
    async with _fav_store.lock:
        favs = _fav_store.load()
        if uid in favs and post_id in favs[uid]:
            favs[uid].remove(post_id)
            if not favs[uid]:
                favs.pop(uid)
            _fav_store.save(favs)

    # Remove from all tags if present
    async with _tags_lock:
        tags = _load_tags()
        changed = False
        for tag_name in list(tags.keys()):
            uid_map = tags[tag_name]
            if uid in uid_map and post_id in uid_map[uid]:
                uid_map[uid].remove(post_id)
                if not uid_map[uid]:
                    uid_map.pop(uid)
                if not uid_map:
                    tags.pop(tag_name)
                changed = True
        if changed:
            _save_tags(tags)

    return {"ok": True}


@router.post("/api/refresh")
async def api_refresh(full: bool = False):
    if full:
        await asyncio.to_thread(_build_index_full)
    else:
        await asyncio.to_thread(_build_index)
    return {"ok": True, "count": len(posts_index)}


# ── app factory ──────────────────────────────────────────


def create_app() -> FastAPI:
    app = FastAPI(
        title="Weibo Image Web",
        lifespan=build_lifespan(
            _build_index, AUTO_REFRESH_INTERVAL, on_startup=_startup_thumbnails
        ),
    )
    setup_cors(app)
    add_cache_headers_middleware(app, max_age=31536000, immutable=True)

    app.include_router(router)
    register_favorite_mutations(app, _fav_store)

    THUMB_DIR.mkdir(parents=True, exist_ok=True)
    app.mount(
        "/media/thumbnails",
        StaticFiles(directory=str(THUMB_DIR)),
        name="media-thumbnails",
    )
    if WEIBO_MSG_DIR.is_dir():
        app.mount("/media", StaticFiles(directory=str(WEIBO_MSG_DIR)), name="media")

    mount_frontend(app, FRONTEND_DIST)
    return app


app = create_app()
