"""web/web_search：DuckDuckGo 搜索（获取信息的首选工具）。

复用 pydantic-ai common_tools 的实现，但用更明确的描述引导模型：想了解信息时
优先用这个，只有拿到具体网址、需要全文时才用 ``web_fetch``。
"""

from __future__ import annotations

try:
    from pydantic_ai.common_tools.duckduckgo import duckduckgo_search_tool as _search
except ImportError:  # ddgs 未安装 → 工具不注入
    _search = None

if _search is not None:
    from pydantic_ai.tools import Tool

    _orig = _search(max_results=5)
    tool = Tool(
        _orig.function,
        name=_orig.name,
        description=(
            "搜索网页获取最新信息、事实或资料。"
            "想了解某件事时优先用这个工具；"
            "只有当你已经有具体网址、需要它的全文时才用 web_fetch。"
        ),
    )
else:
    tool = None
