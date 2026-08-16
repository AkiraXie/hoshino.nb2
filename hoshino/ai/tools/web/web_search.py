"""web/web_search：DuckDuckGo 搜索（获取信息的首选工具）。

复用 pydantic-ai common_tools 的实现（``DuckDuckGoSearchTool``），但客户端改为
每次调用时按 ``AI_TOOL_USE_PROXY`` 实时构造：开启时把工具代理传给 ddgs（其自身
只认 ``DDGS_PROXY`` 环境变量，不走 AI 配置），且支持 ``ai config`` 在线修改
即时生效；关闭时与旧行为一致（直连）。
"""

from __future__ import annotations

try:
    from ddgs.ddgs import DDGS
    from pydantic_ai.common_tools.duckduckgo import DuckDuckGoSearchTool
    from pydantic_ai.tools import Tool
except ImportError:  # ddgs 未安装 → 工具不注入
    DDGS = None  # type: ignore[assignment]

if DDGS is not None:
    from ... import provider
    from ...config import load_ai_config_from_env

    async def _search(query: str) -> list[dict[str, str]]:
        """搜索网页获取最新信息、事实或资料。

        想了解某件事时优先用这个工具；只有当你已经有具体网址、需要它的全文时
        才用 web_fetch。
        """
        cfg = load_ai_config_from_env()
        client = DDGS(
            proxy=provider.resolve_tool_proxy(cfg.proxy, tool_use_proxy=cfg.tool_use_proxy)
        )
        return await DuckDuckGoSearchTool(client=client, max_results=5)(query)

    tool = Tool(
        _search,
        name="duckduckgo_search",
        description=(
            "搜索网页获取最新信息、事实或资料。"
            "想了解某件事时优先用这个工具；"
            "只有当你已经有具体网址、需要它的全文时才用 web_fetch。"
        ),
    )
else:
    tool = None
