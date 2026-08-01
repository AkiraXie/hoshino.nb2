"""X Image Web provider —— X/Twitter 瀑布流图片浏览站点（冷蓝色调）。

数据源为 ``data/db/x.db`` 的 outbox（已发送帖子）与 ``data/x/`` 本地媒体；远程图片经
``/media/proxy`` 代理缓存。前端位于 ``x_image_web/frontend``。
"""

import asyncio
import hashlib
import json
import sqlite3
import threading
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from PIL import Image

from image_web.common.env import read_env_data_dir
from image_web.common.favorites import FavoritesStore, register_favorite_mutations
from image_web.common.lifecycle import build_lifespan
from image_web.common.middleware import add_cache_headers_middleware, setup_cors
from image_web.common.pagination import paginate
from image_web.common.spa import mount_frontend

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent.parent

DATA_DIR = read_env_data_dir(PROJECT_ROOT)
X_DB_PATH = DATA_DIR / "db" / "x.db"
X_MEDIA_DIR = DATA_DIR / "x"
THUMB_DIR = DATA_DIR / "x_thumbnails"
MEDIA_CACHE_DIR = DATA_DIR / "x_media_cache"
FAV_JSON = DATA_DIR / "x_favorite.json"
FRONTEND_DIST = PROJECT_ROOT / "x_image_web" / "frontend" / "dist"

AUTO_REFRESH_INTERVAL = 5 * 60  # seconds

posts_index: list[dict] = []
uid_nickname_map: dict[str, str] = {}
_build_lock = threading.RLock()
_http_client: httpx.AsyncClient | None = None

_fav_store = FavoritesStore(FAV_JSON)


def _get_http_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(
            timeout=30.0,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (compatible; XImageWeb/1.0)"},
        )
    return _http_client


async def _shutdown_client() -> None:
    global _http_client
    if _http_client:
        await _http_client.aclose()
        _http_client = None


# ── helpers ──────────────────────────────────────────────


def _rewrite_media_path(path: str) -> str:
    """Rewrite absolute local paths to /media/x/... URLs; pass remote URLs through."""
    if path.startswith(("http://", "https://")):
        return path
    # Local path: extract the part after data/x/
    x_dir_str = str(X_MEDIA_DIR)
    if path.startswith(x_dir_str):
        relative = path[len(x_dir_str) :].lstrip("/")
        return f"/media/x/{relative}"
    # Fallback: try to find data/x/ in the path
    marker = "/data/x/"
    idx = path.find(marker)
    if idx >= 0:
        relative = path[idx + len(marker) :]
        return f"/media/x/{relative}"
    return path


def _parse_x_post_payload(payload: dict) -> dict:
    """Parse an XPost dict (from outbox JSON) into an index entry."""
    uid = str(payload.get("uid") or "")
    post_id = str(payload.get("id") or "")
    content = str(payload.get("content") or "")
    nickname = str(payload.get("nickname") or "") or uid
    timestamp = float(payload.get("timestamp") or 0)
    url = str(payload.get("url") or "")
    images = [_rewrite_media_path(p) for p in (payload.get("images") or [])]
    videos = [_rewrite_media_path(p) for p in (payload.get("videos") or [])]
    likes = int(payload.get("likes") or 0)

    # Handle repost
    repost = payload.get("repost")
    repost_info = None
    if isinstance(repost, dict):
        repost_info = {
            "uid": str(repost.get("uid") or ""),
            "nickname": str(repost.get("nickname") or ""),
            "content": str(repost.get("content") or ""),
            "url": str(repost.get("url") or ""),
        }

    cover = images[0] if images else None

    return {
        "uid": uid,
        "id": post_id,
        "content": content,
        "nickname": nickname,
        "timestamp": timestamp,
        "url": url,
        "likes": likes,
        "image_count": len(images),
        "video_count": len(videos),
        "images": images,
        "videos": videos,
        "cover": cover,
        "repost": repost_info,
    }


def _build_index() -> None:
    """Build posts index from x.db outbox (sent posts)."""
    global posts_index, uid_nickname_map

    with _build_lock:
        if not X_DB_PATH.exists():
            posts_index = []
            uid_nickname_map = {}
            return

        index: list[dict] = []
        umap: dict[str, str] = {}
        seen: set[str] = set()

        try:
            conn = sqlite3.connect(str(X_DB_PATH), timeout=10)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT username, tweet_id, payload FROM outbox
                WHERE status = 'sent'
                ORDER BY CAST(tweet_id AS INTEGER) DESC
                """
            ).fetchall()
            conn.close()
        except (sqlite3.Error, OSError):
            return

        for row in rows:
            tweet_id = str(row["tweet_id"])
            if tweet_id in seen:
                continue
            seen.add(tweet_id)

            try:
                payload = json.loads(row["payload"])
            except (json.JSONDecodeError, TypeError):
                continue

            entry = _parse_x_post_payload(payload)
            if entry["nickname"]:
                umap.setdefault(entry["uid"], entry["nickname"])
            index.append(entry)

        index.sort(key=lambda e: e.get("timestamp") or 0, reverse=True)
        posts_index = index
        uid_nickname_map = umap


def _url_suffix(url: str) -> str:
    """Extract file suffix from URL."""
    path = urlparse(url).path.lower()
    for ext in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
        if path.endswith(ext):
            return ext
    return ".jpg"


def _url_cache_key(url: str) -> str:
    """Generate a safe filename from a URL."""
    return hashlib.sha256(url.encode()).hexdigest()[:32] + _url_suffix(url)


def _generate_thumbnail(uid: str, post_id: str, image_url: str) -> str | None:
    """Download and cache a thumbnail for a remote image. Returns local path or None."""
    thumb_dir = THUMB_DIR / uid / post_id
    thumb_dir.mkdir(parents=True, exist_ok=True)
    webp_dest = thumb_dir / "cover.webp"
    jpg_dest = thumb_dir / "cover.jpg"

    if webp_dest.exists():
        return str(webp_dest)
    if jpg_dest.exists():
        return str(jpg_dest)

    # Check media cache first
    cache_key = _url_cache_key(image_url)
    cached = MEDIA_CACHE_DIR / cache_key
    if cached.exists():
        try:
            img = Image.open(cached)
            img.thumbnail((600, 800))
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            img.save(webp_dest, "WEBP", quality=82)
            return str(webp_dest)
        except Exception:
            pass

    return None


def _summary(p: dict) -> dict:
    return {
        "uid": p["uid"],
        "id": p["id"],
        "content": p["content"],
        "nickname": p["nickname"],
        "timestamp": p["timestamp"],
        "url": p["url"],
        "likes": p["likes"],
        "image_count": p["image_count"],
        "video_count": p["video_count"],
        "cover": p["cover"],
    }


# ── API routes ───────────────────────────────────────────

router = APIRouter()


@router.get("/api/posts")
async def api_list_posts(page: int = 1, size: int = 20, uid: str = "", q: str = ""):
    await asyncio.to_thread(_build_index)
    results = list(posts_index)
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
    total, page_items = paginate(results, page, size)
    items = []
    for p in page_items:
        item = _summary(p)
        item["repost"] = p.get("repost")
        items.append(item)
    return {"total": total, "page": page, "size": size, "items": items}


@router.get("/api/posts/{uid}/{post_id}")
async def api_get_post(uid: str, post_id: str):
    entry = next(
        (p for p in posts_index if p["uid"] == uid and p["id"] == post_id), None
    )
    if not entry:
        raise HTTPException(404, "Post not found")
    return entry


@router.get("/api/uids")
async def api_list_uids():
    return uid_nickname_map


@router.get("/api/stats/top-uids")
async def api_top_uids(limit: int = 5, preview: int = 4):
    uid_counts = Counter(p["uid"] for p in posts_index)
    top = uid_counts.most_common(limit)
    result = []
    for uid, count in top:
        posts = [_summary(p) for p in posts_index if p["uid"] == uid][:preview]
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
    fav_set = {f"{uid}_{pid}" for uid, ids in favs.items() for pid in ids}
    fav_posts = [p for p in posts_index if f"{p['uid']}_{p['id']}" in fav_set]
    total, page_items = paginate(fav_posts, page, size)
    items = [_summary(p) for p in page_items]
    return {"total": total, "page": page, "size": size, "items": items}


@router.get("/api/favorites/ids")
async def api_favorite_ids():
    favs = _fav_store.load()
    return [f"{uid}_{pid}" for uid, ids in favs.items() for pid in ids]


# ── Media proxy ──────────────────────────────────────────


@router.get("/media/proxy")
async def media_proxy(url: str):
    """Proxy remote images to avoid CORS/hotlink issues and enable caching."""
    if not url.startswith(("http://", "https://")):
        raise HTTPException(400, "Invalid URL")

    cache_key = _url_cache_key(url)
    cached_path = MEDIA_CACHE_DIR / cache_key

    if cached_path.exists():
        media_type = "image/webp" if cache_key.endswith(".webp") else "image/jpeg"
        if ".png" in cache_key:
            media_type = "image/png"
        elif ".gif" in cache_key:
            media_type = "image/gif"
        return FileResponse(cached_path, media_type=media_type)

    # Download and cache
    try:
        client = _get_http_client()
        resp = await client.get(url)
        resp.raise_for_status()
    except Exception as e:
        raise HTTPException(502, f"Failed to fetch image: {e}")

    content_type = resp.headers.get("content-type", "image/jpeg")
    MEDIA_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cached_path.write_bytes(resp.content)

    return Response(content=resp.content, media_type=content_type)


@router.post("/api/refresh")
async def api_refresh():
    await asyncio.to_thread(_build_index)
    return {"ok": True, "count": len(posts_index)}


# ── app factory ──────────────────────────────────────────


def create_app() -> FastAPI:
    app = FastAPI(
        title="X Image Web",
        lifespan=build_lifespan(
            _build_index, AUTO_REFRESH_INTERVAL, on_shutdown=_shutdown_client
        ),
    )
    setup_cors(app)
    add_cache_headers_middleware(app, max_age=86400)

    app.include_router(router)
    register_favorite_mutations(app, _fav_store)

    THUMB_DIR.mkdir(parents=True, exist_ok=True)
    MEDIA_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    # Serve local X media (downloaded images/videos under data/x/)
    if X_MEDIA_DIR.is_dir():
        app.mount("/media/x", StaticFiles(directory=str(X_MEDIA_DIR)), name="x-media")

    mount_frontend(app, FRONTEND_DIST)
    return app


app = create_app()
