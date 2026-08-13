"""web/web_search：DuckDuckGo 搜索，复用 pydantic-ai common_tools。

``ddgs`` 为可选依赖；缺失时模块级置 None，该工具不注入（与 plan 的守卫约定一致）。
"""

from __future__ import annotations

try:
    from pydantic_ai.common_tools.duckduckgo import duckduckgo_search_tool as _search
except ImportError:  # ddgs 未安装 → 工具不注入
    _search = None

tool = _search(max_results=5) if _search is not None else None
