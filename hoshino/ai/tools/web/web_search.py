"""web/web_search：原生联网搜索工具（provider 解耦，deepseek / tavily / 博查）。

工具本身只做配置解析与代理透传：搜索 provider 由 ``ai search`` 单独配置
（``hoshino/ai/search.py``，默认 deepseek），与聊天 provider / vision 平级。
三种 provider 的实现（Anthropic Messages + 服务端 web_search_20250305 /
Tavily API / 博查 API）都在 ``hoshino.ai.search``，工具返回结构化结果文本，
由调用（text）模型基于结果作答。
"""

from __future__ import annotations

from pydantic_ai import RunContext

from ... import provider, search
from ...deps import AgentDeps


async def web_search(ctx: RunContext[AgentDeps], query: str) -> str:
    """搜索网页获取最新信息、事实或资料（deepseek / tavily / 博查）。

    想了解某件事时优先用这个工具；只有当你已经有具体网址、需要它的全文时
    才用 web_fetch。搜索 provider 由管理员配置（`ai search`），未配置时
    返回提示。
    """
    cfg = search.resolve_search_config(ctx.deps.scope_key, ctx.deps.config)
    if cfg is None:
        return (
            "当前未配置搜索 provider：`ai search set <deepseek|tavily|bocha> ...`"
            "（默认 deepseek，需 anthropic 兼容聊天 provider 或显式 --key）。"
        )
    return await search.search_web(
        cfg,
        query,
        proxy=provider.resolve_tool_proxy(
            ctx.deps.config.proxy, tool_use_proxy=ctx.deps.config.tool_use_proxy
        ),
        verify=ctx.deps.config.web_fetch_verify_ssl,
    )


tool = web_search
