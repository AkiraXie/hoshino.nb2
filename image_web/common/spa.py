from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles


def mount_frontend(app: FastAPI, dist_dir: Path) -> None:
    """挂载构建后的前端静态资源与 SPA catch-all。

    必须在所有 API 路由和媒体挂载之后调用，否则 catch-all 会吞掉其它路径。
    """
    if dist_dir.is_dir() and (dist_dir / "assets").is_dir():
        app.mount(
            "/assets",
            StaticFiles(directory=str(dist_dir / "assets")),
            name="frontend-assets",
        )

    @app.get("/{path:path}")
    async def serve_spa(path: str):
        if not dist_dir.is_dir():
            raise HTTPException(
                404, "Frontend not built. Run: cd frontend && npm run build"
            )
        if ".." in path:
            raise HTTPException(400)
        file = (dist_dir / path).resolve()
        dist_resolved = dist_dir.resolve()
        if file.is_file() and str(file).startswith(str(dist_resolved)):
            return FileResponse(file)
        index = dist_resolved / "index.html"
        if index.is_file():
            return FileResponse(index)
        raise HTTPException(404)
