"""兼容出口：SSRF helper 已下沉到 ``hoshino.ai.net``（避免 tools↔media 循环）。"""

from __future__ import annotations

from hoshino.ai.net import is_private_host

__all__ = ["is_private_host"]
