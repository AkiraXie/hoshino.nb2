"""内容订阅共享契约 — compat re-export from hoshino.content"""

from hoshino.content import (
    Post,
    PostMessage,
    PostQueue,
    PostResource,
    Queueable,
    RenderableMessage,
    UIDManager,
    clean_filename,
)

__all__ = [
    "Post",
    "PostMessage",
    "PostQueue",
    "PostResource",
    "Queueable",
    "RenderableMessage",
    "UIDManager",
    "clean_filename",
]
