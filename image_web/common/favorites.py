import asyncio
from collections.abc import Callable
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from .jsonstore import load_json, save_json


class FavoritesStore:
    """收藏 JSON（{uid: [post_id, ...]}）的读写与并发锁。"""

    def __init__(self, path: Path):
        self.path = path
        self.lock = asyncio.Lock()

    def load(self) -> dict[str, list[str]]:
        data = load_json(self.path, {})
        if not isinstance(data, dict):
            return {}
        return {
            str(uid): [str(pid) for pid in ids]
            for uid, ids in data.items()
            if isinstance(ids, list)
        }

    def save(self, favs: dict[str, list[str]]) -> None:
        save_json(self.path, favs)


class FavBody(BaseModel):
    uid: str
    id: str


def register_favorite_mutations(app: FastAPI, store: FavoritesStore) -> None:
    """注册两端逐字节相同的收藏写入接口：POST /api/favorites 与 DELETE。

    收藏的"读取"接口（list/ids）因序列化和黑名单差异保留在各 provider。
    """

    @app.post("/api/favorites")
    async def api_add_favorite(body: FavBody):
        async with store.lock:
            favs = store.load()
            ids = favs.get(body.uid, [])
            if body.id in ids:
                return {"ok": True}
            ids.append(body.id)
            favs[body.uid] = ids
            store.save(favs)
        return {"ok": True}

    @app.delete("/api/favorites/{uid}/{post_id}")
    async def api_remove_favorite(uid: str, post_id: str):
        async with store.lock:
            favs = store.load()
            ids = favs.get(uid, [])
            if post_id not in ids:
                raise HTTPException(404, "Not in favorites")
            ids.remove(post_id)
            if ids:
                favs[uid] = ids
            else:
                favs.pop(uid, None)
            store.save(favs)
        return {"ok": True}


GetIndex = Callable[[], list[dict]]
