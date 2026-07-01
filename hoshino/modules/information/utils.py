"""内容订阅共享契约 — compat re-export from hoshino.content"""
from hoshino.content import (
    Post,
    PostMessage,
    PostQueue,
    UIDManager,
    clean_filename,
    Queueable,
    RenderableMessage,
    PostResource,
)

__all__ = [
    "Post",
    "PostMessage",
    "PostQueue",
    "UIDManager",
    "clean_filename",
    "Queueable",
    "RenderableMessage",
    "PostResource",
]
