"""X Image Web - X/Twitter 瀑布流图片浏览站点（冷蓝色调）"""

import asyncio
import json
import sqlite3
import threading
from collections import Counter
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from PIL import Image
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
X_DB_PATH = DATA_DIR / "db" / "x.db"
X_MEDIA_DIR = DATA_DIR / "x"
THUMB_DIR = DATA_DIR / "x_thumbnails"
MEDIA_CACHE_DIR = DATA_DIR / "x_media_cache"
FRONTEND_DIST = BASE_DIR / "frontend" / "dist"

FAV_JSON = DATA_DIR / "x_favorite.json"

posts_index: list[dict] = []
uid_nickname_map: dict[str, str] = {}
_build_lock = threading.RLock()
_fav_lock: asyncio.Lock | None = None
_http_client: httpx.AsyncClient | None = None


def _get_fav_lock() -> asyncio.Lock:
    global _fav_lock
    if _fav_lock is None:
        _fav_lock = asyncio.Lock()
    return _fav_lock


def _get_http_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(
            timeout=30.0,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (compatible; XImageWeb/1.0)"},
        )
    return _http_client


# ── helpers ──────────────────────────────────────────────


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


def _url_cache_key(url: str) -> str:
    """Generate a safe filename from a URL."""
    import hashlib

    return hashlib.sha256(url.encode()).hexdigest()[:32] + _url_suffix(url)


def _url_suffix(url: str) -> str:
    """Extract file suffix from URL."""
    from urllib.parse import urlparse

    path = urlparse(url).path.lower()
    for ext in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
        if path.endswith(ext):
            return ext
    return ".jpg"


# ── app ──────────────────────────────────────────────────

AUTO_REFRESH_INTERVAL = 5 * 60  # seconds


async def _auto_refresh_loop():
    while True:
        await asyncio.sleep(AUTO_REFRESH_INTERVAL)
        await asyncio.to_thread(_build_index)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await asyncio.to_thread(_build_index)
    task = asyncio.create_task(_auto_refresh_loop())
    yield
    task.cancel()
    global _http_client
    if _http_client:
        await _http_client.aclose()
        _http_client = None


app = FastAPI(title="X Image Web", lifespan=lifespan)

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
        response.headers["Cache-Control"] = "public, max-age=86400"
    return response


# ── models ───────────────────────────────────────────────


class FavBody(BaseModel):
    uid: str
    id: str


# ── API routes ───────────────────────────────────────────


@app.get("/api/posts")
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
    total = len(results)
    start = (page - 1) * size
    # Strip full images/videos list from summary
    items = []
    for p in results[start : start + size]:
        items.append(
            {
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
                "repost": p.get("repost"),
            }
        )
    return {"total": total, "page": page, "size": size, "items": items}


@app.get("/api/posts/{uid}/{post_id}")
async def api_get_post(uid: str, post_id: str):
    entry = next(
        (p for p in posts_index if p["uid"] == uid and p["id"] == post_id), None
    )
    if not entry:
        raise HTTPException(404, "Post not found")
    return entry


@app.get("/api/uids")
async def api_list_uids():
    return uid_nickname_map


@app.get("/api/stats/top-uids")
async def api_top_uids(limit: int = 5, preview: int = 4):
    uid_counts = Counter(p["uid"] for p in posts_index)
    top = uid_counts.most_common(limit)
    result = []
    for uid, count in top:
        posts = [
            {
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
            for p in posts_index
            if p["uid"] == uid
        ][:preview]
        result.append(
            {
                "uid": uid,
                "nickname": uid_nickname_map.get(uid, uid),
                "count": count,
                "posts": posts,
            }
        )
    return result


# ── Favorites API ────────────────────────────────────────


@app.get("/api/favorites")
async def api_list_favorites(page: int = 1, size: int = 20):
    favs = _load_favs()
    fav_set = {f"{uid}_{pid}" for uid, ids in favs.items() for pid in ids}
    fav_posts = [p for p in posts_index if f"{p['uid']}_{p['id']}" in fav_set]
    total = len(fav_posts)
    start = (page - 1) * size
    items = [
        {
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
        for p in fav_posts[start : start + size]
    ]
    return {"total": total, "page": page, "size": size, "items": items}


@app.get("/api/favorites/ids")
async def api_favorite_ids():
    favs = _load_favs()
    return [f"{uid}_{pid}" for uid, ids in favs.items() for pid in ids]


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


# ── Media proxy ──────────────────────────────────────────


@app.get("/media/proxy")
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


@app.post("/api/refresh")
async def api_refresh():
    await asyncio.to_thread(_build_index)
    return {"ok": True, "count": len(posts_index)}


# ── static files ─────────────────────────────────────────

THUMB_DIR.mkdir(parents=True, exist_ok=True)
MEDIA_CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Serve local X media (downloaded images/videos under data/x/)
if X_MEDIA_DIR.is_dir():
    app.mount("/media/x", StaticFiles(directory=str(X_MEDIA_DIR)), name="x-media")

if FRONTEND_DIST.is_dir() and (FRONTEND_DIST / "assets").is_dir():
    app.mount(
        "/assets",
        StaticFiles(directory=str(FRONTEND_DIST / "assets")),
        name="frontend-assets",
    )


@app.get("/{path:path}")
async def serve_spa(path: str):
    if not FRONTEND_DIST.is_dir():
        raise HTTPException(
            404, "Frontend not built. Run: cd frontend && npm run build"
        )
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

    uvicorn.run(app, host="0.0.0.0", port=9997)
