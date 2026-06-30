"""Weibo Image Web - 微博瀑布流图片浏览站点"""

import asyncio
import json
import os
import re
import shutil
import threading
from collections import Counter
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent


def _read_env_data_dir() -> Path:
    """从 .env.prod 读取 data 配置项，返回绝对路径。"""
    env_file = PROJECT_ROOT / ".env.prod"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            if key.strip() == "data":
                p = Path(value.strip())
                return p if p.is_absolute() else PROJECT_ROOT / p
    return PROJECT_ROOT / "data"


DATA_DIR = _read_env_data_dir()
WEIBO_MSG_DIR = DATA_DIR / "weibomsgs"
THUMB_DIR = DATA_DIR / "thumbnails"
TRASH_DIR = DATA_DIR / "weibomsgs_trash"
FAV_JSON = DATA_DIR / "weibofavorite.json"
TAGS_JSON = DATA_DIR / "weibotags.json"
BLACKLIST_JSON = DATA_DIR / "weiboblacklist.json"
INDEX_CACHE = DATA_DIR / "index_cache.json"
FRONTEND_DIST = BASE_DIR / "frontend" / "dist"

posts_index: list[dict] = []
uid_nickname_map: dict[str, str] = {}
# {uid}_{post_id} -> dir mtime, used for incremental refresh
_post_mtimes: dict[str, float] = {}
# uid_dir mtime snapshot, detect which uid dirs changed
_uid_dir_mtimes: dict[str, float] = {}
_build_lock = threading.RLock()
_fav_lock: asyncio.Lock | None = None
_tags_lock: asyncio.Lock | None = None
_blacklist_lock: asyncio.Lock | None = None


def _get_fav_lock() -> asyncio.Lock:
    global _fav_lock
    if _fav_lock is None:
        _fav_lock = asyncio.Lock()
    return _fav_lock


def _get_tags_lock() -> asyncio.Lock:
    global _tags_lock
    if _tags_lock is None:
        _tags_lock = asyncio.Lock()
    return _tags_lock


def _get_blacklist_lock() -> asyncio.Lock:
    global _blacklist_lock
    if _blacklist_lock is None:
        _blacklist_lock = asyncio.Lock()
    return _blacklist_lock


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
        from PIL import Image

        img = Image.open(source_path)
        img.thumbnail((600, 800))
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        img.save(jpg_dest, "JPEG", quality=82, optimize=True)
        img.save(webp_dest, "WEBP", quality=82, optimize=True)
        return True
    except Exception:
        return False


def _load_favs() -> dict[str, list[str]]:
    if not FAV_JSON.exists():
        return {}
    try:
        data = json.loads(FAV_JSON.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {
        str(uid): [str(pid) for pid in ids]
        for uid, ids in data.items()
        if isinstance(ids, list)
    }


def _save_favs(favs: dict[str, list[str]]) -> None:
    FAV_JSON.write_text(
        json.dumps(favs, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _load_blacklist() -> list[str]:
    """Load blacklisted UIDs."""
    if not BLACKLIST_JSON.exists():
        return []
    try:
        data = json.loads(BLACKLIST_JSON.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(data, list):
        return []
    return [str(uid) for uid in data]


def _save_blacklist(uids: list[str]) -> None:
    BLACKLIST_JSON.write_text(
        json.dumps(uids, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _load_tags() -> dict[str, dict[str, list[str]]]:
    """Load tags: {tag_name: {uid: [post_ids]}}"""
    if not TAGS_JSON.exists():
        return {}
    try:
        data = json.loads(TAGS_JSON.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    return data


def _save_tags(tags: dict[str, dict[str, list[str]]]) -> None:
    TAGS_JSON.write_text(
        json.dumps(tags, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _scan_post(uid: str, post_dir: Path) -> dict:
    """Scan a single post directory and return its index entry."""
    post_id = post_dir.name
    meta_path = post_dir / "message.json"
    meta: dict = {}
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass

    images_dir = post_dir / "images"
    image_count = (
        len(list(images_dir.glob("*.jpg"))) if images_dir.is_dir() else 0
    )
    videos_dir = post_dir / "videos"
    video_count = (
        len(list(videos_dir.glob("*.mp4"))) if videos_dir.is_dir() else 0
    )

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


def _load_index_cache() -> tuple[list[dict], dict[str, float], dict[str, float]] | None:
    """Load cached index from disk. Returns (entries, post_mtimes, uid_dir_mtimes) or None."""
    if not INDEX_CACHE.exists():
        return None
    try:
        data = json.loads(INDEX_CACHE.read_text(encoding="utf-8"))
        entries = data["entries"]
        p_mtimes = data.get("post_mtimes", {})
        u_mtimes = data.get("uid_dir_mtimes", {})
        return entries, p_mtimes, u_mtimes
    except (OSError, json.JSONDecodeError, KeyError):
        return None


def _save_index_cache() -> None:
    """Persist current index to disk for fast startup."""
    data = {
        "entries": posts_index,
        "post_mtimes": _post_mtimes,
        "uid_dir_mtimes": _uid_dir_mtimes,
    }
    INDEX_CACHE.write_text(
        json.dumps(data, ensure_ascii=False), encoding="utf-8"
    )


def _build_index_full() -> None:
    """Full rebuild — scan everything from scratch."""
    global posts_index, uid_nickname_map, _post_mtimes, _uid_dir_mtimes

    with _build_lock:
        index: list[dict] = []
        umap: dict[str, str] = {}
        p_mtimes: dict[str, float] = {}
        u_mtimes: dict[str, float] = {}

        if not WEIBO_MSG_DIR.is_dir():
            posts_index, uid_nickname_map = [], {}
            _post_mtimes, _uid_dir_mtimes = {}, {}
            return

        for uid_dir in WEIBO_MSG_DIR.iterdir():
            if not uid_dir.is_dir():
                continue
            uid = uid_dir.name
            try:
                u_mtimes[uid] = uid_dir.stat().st_mtime
            except OSError:
                continue
            for post_dir in uid_dir.iterdir():
                if not post_dir.is_dir():
                    continue
                post_id = post_dir.name
                try:
                    p_mtimes[f"{uid}_{post_id}"] = post_dir.stat().st_mtime
                except OSError:
                    continue
                entry = _scan_post(uid, post_dir)
                if entry["nickname"]:
                    umap.setdefault(uid, entry["nickname"])
                index.append(entry)

        index.sort(key=lambda e: e.get("timestamp") or 0, reverse=True)
        posts_index = index
        uid_nickname_map = umap
        _post_mtimes = p_mtimes
        _uid_dir_mtimes = u_mtimes
        _save_index_cache()


def _build_index_incremental() -> int:
    """Incremental refresh — only rescan changed uid directories.

    Returns the number of posts added/updated/removed.
    """
    global posts_index, uid_nickname_map, _post_mtimes, _uid_dir_mtimes

    if not WEIBO_MSG_DIR.is_dir():
        if posts_index:
            posts_index, uid_nickname_map = [], {}
            _post_mtimes, _uid_dir_mtimes = {}, {}
            _save_index_cache()
        return 0

    changes = 0

    # 1. Discover current uid dirs on disk
    current_uids: dict[str, float] = {}
    for uid_dir in WEIBO_MSG_DIR.iterdir():
        if not uid_dir.is_dir():
            continue
        try:
            current_uids[uid_dir.name] = uid_dir.stat().st_mtime
        except OSError:
            continue

    # 2. Find removed uids
    removed_uids = set(_uid_dir_mtimes.keys()) - set(current_uids.keys())
    if removed_uids:
        posts_index = [p for p in posts_index if p["uid"] not in removed_uids]
        for uid in removed_uids:
            _uid_dir_mtimes.pop(uid, None)
            uid_nickname_map.pop(uid, None)
        _post_mtimes = {k: v for k, v in _post_mtimes.items()
                        if k.split("_", 1)[0] not in removed_uids}
        changes += 1

    # 3. Find uid dirs with changed mtime (new posts added/removed inside)
    changed_uids: set[str] = set()
    for uid, mtime in current_uids.items():
        old_mtime = _uid_dir_mtimes.get(uid)
        if old_mtime is None or mtime != old_mtime:
            changed_uids.add(uid)

    if not changed_uids and not removed_uids:
        return 0  # nothing changed

    # 4. For each changed uid dir, diff its posts
    for uid in changed_uids:
        uid_dir = WEIBO_MSG_DIR / uid
        _uid_dir_mtimes[uid] = current_uids[uid]

        # Current posts on disk
        disk_posts: dict[str, float] = {}
        for post_dir in uid_dir.iterdir():
            if not post_dir.is_dir():
                continue
            try:
                disk_posts[post_dir.name] = post_dir.stat().st_mtime
            except OSError:
                continue

        # Previously indexed posts for this uid
        old_post_ids = {
            k.split("_", 1)[1]
            for k in _post_mtimes
            if k.startswith(f"{uid}_")
        }

        # Removed posts
        removed_ids = old_post_ids - set(disk_posts.keys())
        if removed_ids:
            remove_keys = {f"{uid}_{pid}" for pid in removed_ids}
            posts_index = [
                p for p in posts_index
                if f"{p['uid']}_{p['id']}" not in remove_keys
            ]
            for pid in removed_ids:
                _post_mtimes.pop(f"{uid}_{pid}", None)
            changes += len(removed_ids)

        # New or updated posts
        for post_id, mtime in disk_posts.items():
            key = f"{uid}_{post_id}"
            old_mtime = _post_mtimes.get(key)
            if old_mtime is not None and mtime == old_mtime:
                continue  # unchanged
            # Rescan this post
            post_dir = uid_dir / post_id
            entry = _scan_post(uid, post_dir)
            _post_mtimes[key] = mtime

            if entry["nickname"]:
                uid_nickname_map.setdefault(uid, entry["nickname"])

            if old_mtime is not None:
                # Updated — replace in-place
                posts_index = [
                    entry if (p["uid"] == uid and p["id"] == post_id) else p
                    for p in posts_index
                ]
            else:
                # New post
                posts_index.append(entry)
            changes += 1

    if changes:
        posts_index.sort(key=lambda e: e.get("timestamp") or 0, reverse=True)
        _save_index_cache()

    return changes


def _build_index() -> None:
    """Smart index build: load cache on first call, then incremental."""
    global posts_index, uid_nickname_map, _post_mtimes, _uid_dir_mtimes

    with _build_lock:
        if not posts_index:
            cached = _load_index_cache()
            if cached is not None:
                entries, p_mtimes, u_mtimes = cached
                posts_index = entries
                _post_mtimes = p_mtimes
                _uid_dir_mtimes = u_mtimes
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


# ── app ──────────────────────────────────────────────────


AUTO_REFRESH_INTERVAL = 30 * 60  # seconds


async def _auto_refresh_loop():
    while True:
        await asyncio.sleep(AUTO_REFRESH_INTERVAL)
        await asyncio.to_thread(_build_index)


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


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await asyncio.to_thread(_build_index)
    task = asyncio.create_task(_auto_refresh_loop())
    asyncio.create_task(asyncio.to_thread(_generate_all_missing_thumbnails))
    yield
    task.cancel()


app = FastAPI(title="Weibo Image Web", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_cache_headers(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/media/"):
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    return response


# ── models ───────────────────────────────────────────────


class FavBody(BaseModel):
    uid: str
    id: str


class TagBody(BaseModel):
    uid: str
    id: str
    tag: str


class BlacklistBody(BaseModel):
    uid: str


# ── API routes ───────────────────────────────────────────


@app.get("/api/posts")
async def api_list_posts(
    page: int = 1, size: int = 20, uid: str = "", q: str = "", date: str = ""
):
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
        results = [
            p for p in results if ts_min <= (p.get("timestamp") or 0) < ts_max
        ]
    total = len(results)
    start = (page - 1) * size
    return {
        "total": total,
        "page": page,
        "size": size,
        "items": results[start : start + size],
    }


@app.get("/api/posts/{uid}/{post_id}")
async def api_get_post(uid: str, post_id: str):
    entry = next(
        (p for p in posts_index if p["uid"] == uid and p["id"] == post_id), None
    )
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
    screenshot = (
        f"/media/{uid}/{post_id}/screenshot.jpg"
        if entry["has_screenshot"]
        else None
    )
    return {**entry, "images": images, "videos": videos, "screenshot": screenshot}


@app.get("/api/uids")
async def api_list_uids():
    blacklist = set(_load_blacklist())
    return {uid: nick for uid, nick in uid_nickname_map.items() if uid not in blacklist}


@app.get("/api/uid-stats")
async def api_uid_stats():
    """Per-uid statistics: total images, favorited post count."""
    favs = _load_favs()
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


@app.get("/api/stats/top-uids")
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


@app.get("/api/favorites")
async def api_list_favorites(page: int = 1, size: int = 20):
    favs = _load_favs()
    blacklist = set(_load_blacklist())
    fav_set = {f"{uid}_{pid}" for uid, ids in favs.items() for pid in ids}
    fav_posts = [p for p in posts_index if f"{p['uid']}_{p['id']}" in fav_set and p["uid"] not in blacklist]
    total = len(fav_posts)
    start = (page - 1) * size
    return {
        "total": total,
        "page": page,
        "size": size,
        "items": fav_posts[start : start + size],
    }


@app.get("/api/favorites/ids")
async def api_favorite_ids():
    favs = _load_favs()
    blacklist = set(_load_blacklist())
    return [f"{uid}_{pid}" for uid, ids in favs.items() if uid not in blacklist for pid in ids]


@app.post("/api/favorites")
async def api_add_favorite(body: FavBody):
    async with _get_fav_lock():
        favs = _load_favs()
        ids = favs.get(body.uid, [])
        if body.id in ids:
            return {"ok": True}
        ids.append(body.id)
        favs[body.uid] = ids
        _save_favs(favs)
    return {"ok": True}


@app.delete("/api/favorites/{uid}/{post_id}")
async def api_remove_favorite(uid: str, post_id: str):
    async with _get_fav_lock():
        favs = _load_favs()
        ids = favs.get(uid, [])
        if post_id not in ids:
            raise HTTPException(404, "Not in favorites")
        ids.remove(post_id)
        if ids:
            favs[uid] = ids
        else:
            favs.pop(uid, None)
        _save_favs(favs)
    return {"ok": True}


# ── Blacklist API ────────────────────────────────────────


@app.get("/api/blacklist")
async def api_list_blacklist():
    """Return blacklisted UIDs with nicknames."""
    uids = _load_blacklist()
    return [
        {"uid": uid, "nickname": uid_nickname_map.get(uid, uid)}
        for uid in uids
    ]


@app.post("/api/blacklist")
async def api_add_blacklist(body: BlacklistBody):
    async with _get_blacklist_lock():
        bl = _load_blacklist()
        if body.uid not in bl:
            bl.append(body.uid)
            _save_blacklist(bl)
    return {"ok": True}


@app.delete("/api/blacklist/{uid}")
async def api_remove_blacklist(uid: str):
    async with _get_blacklist_lock():
        bl = _load_blacklist()
        if uid not in bl:
            raise HTTPException(404, "Not in blacklist")
        bl.remove(uid)
        _save_blacklist(bl)
    return {"ok": True}


# ── Tags API ─────────────────────────────────────────────


@app.get("/api/tags")
async def api_list_tags():
    """Return all tags with post counts."""
    tags = _load_tags()
    result = []
    for tag_name, uid_map in tags.items():
        count = sum(len(ids) for ids in uid_map.values())
        result.append({"tag": tag_name, "count": count})
    result.sort(key=lambda t: t["count"], reverse=True)
    return result


@app.get("/api/tags/post-map")
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


@app.get("/api/tags/{tag}")
async def api_tag_posts(tag: str, page: int = 1, size: int = 20):
    """Return posts for a specific tag, paginated."""
    tags = _load_tags()
    uid_map = tags.get(tag, {})
    tag_set = {f"{uid}_{pid}" for uid, ids in uid_map.items() for pid in ids}
    blacklist = set(_load_blacklist())
    tag_posts = [p for p in posts_index if f"{p['uid']}_{p['id']}" in tag_set and p["uid"] not in blacklist]
    total = len(tag_posts)
    start = (page - 1) * size
    return {
        "total": total,
        "page": page,
        "size": size,
        "items": tag_posts[start : start + size],
    }


@app.get("/api/posts/{uid}/{post_id}/tags")
async def api_post_tags(uid: str, post_id: str):
    """Return tags for a specific post."""
    tags = _load_tags()
    result = []
    key = f"{uid}_{post_id}"
    for tag_name, uid_map in tags.items():
        ids = uid_map.get(uid, [])
        if post_id in ids:
            result.append(tag_name)
    return result


@app.post("/api/tags")
async def api_add_tag(body: TagBody):
    """Add a tag to a post."""
    tag = body.tag.strip()
    if not tag:
        raise HTTPException(400, "Tag cannot be empty")
    async with _get_tags_lock():
        tags = _load_tags()
        uid_map = tags.setdefault(tag, {})
        ids = uid_map.get(body.uid, [])
        if body.id not in ids:
            ids.append(body.id)
            uid_map[body.uid] = ids
        _save_tags(tags)
    return {"ok": True}


@app.delete("/api/tags/{tag}/{uid}/{post_id}")
async def api_remove_tag(tag: str, uid: str, post_id: str):
    """Remove a tag from a post."""
    async with _get_tags_lock():
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


@app.delete("/api/tags/{tag}")
async def api_delete_tag(tag: str):
    """Delete an entire tag."""
    async with _get_tags_lock():
        tags = _load_tags()
        if tag not in tags:
            raise HTTPException(404, "Tag not found")
        tags.pop(tag)
        _save_tags(tags)
    return {"ok": True}


@app.delete("/api/posts/{uid}/{post_id}")
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

    # Remove from in-memory index and mtime cache
    global posts_index
    posts_index = [p for p in posts_index if not (p["uid"] == uid and p["id"] == post_id)]
    _post_mtimes.pop(f"{uid}_{post_id}", None)

    # Remove from favorites if present
    async with _get_fav_lock():
        favs = _load_favs()
        if uid in favs and post_id in favs[uid]:
            favs[uid].remove(post_id)
            if not favs[uid]:
                favs.pop(uid)
            _save_favs(favs)

    # Remove from all tags if present
    async with _get_tags_lock():
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


@app.post("/api/refresh")
async def api_refresh(full: bool = False):
    if full:
        await asyncio.to_thread(_build_index_full)
    else:
        await asyncio.to_thread(_build_index)
    return {"ok": True, "count": len(posts_index)}


# ── static files ─────────────────────────────────────────

THUMB_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/media/thumbnails", StaticFiles(directory=str(THUMB_DIR)), name="media-thumbnails")
app.mount("/media", StaticFiles(directory=str(WEIBO_MSG_DIR)), name="media")

if FRONTEND_DIST.is_dir() and (FRONTEND_DIST / "assets").is_dir():
    app.mount(
        "/assets",
        StaticFiles(directory=str(FRONTEND_DIST / "assets")),
        name="frontend-assets",
    )


@app.get("/{path:path}")
async def serve_spa(path: str):
    if not FRONTEND_DIST.is_dir():
        raise HTTPException(404, "Frontend not built. Run: cd frontend && npm run build")
    if ".." in path:
        raise HTTPException(400)
    file = (FRONTEND_DIST / path).resolve()
    dist_resolved = FRONTEND_DIST.resolve()
    if file.is_file() and str(file).startswith(str(dist_resolved)):
        return FileResponse(file)
    index = dist_resolved / "index.html"
    if index.is_file():
        return FileResponse(index)
    raise HTTPException(404)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=9998)
