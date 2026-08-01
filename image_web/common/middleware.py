from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware


def setup_cors(app: FastAPI) -> None:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )


def add_cache_headers_middleware(
    app: FastAPI, max_age: int, immutable: bool = False
) -> None:
    """为 /media/ 响应添加 Cache-Control。"""
    value = f"public, max-age={max_age}"
    if immutable:
        value += ", immutable"

    @app.middleware("http")
    async def add_cache_headers(request: Request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/media/"):
            response.headers["Cache-Control"] = value
        return response
