"""web/web_fetch：抓取网页为 markdown，复用 pydantic-ai common_tools。

``markdownify`` 为可选依赖；默认 ``allow_local_urls=False``（SSRF 防护）。
"""

from __future__ import annotations

try:
    from pydantic_ai.common_tools.web_fetch import web_fetch_tool as _fetch
except ImportError:  # markdownify 未安装 → 工具不注入
    _fetch = None

tool = _fetch() if _fetch is not None else None
