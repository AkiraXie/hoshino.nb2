"""通用 Agent runner：把 ``agent.iter()`` 包装成异步生成器。

pydantic-ai 的一次 run 是循环图（UserPromptNode → ModelRequestNode → CallToolsNode →
… → End(FinalResult)）。``agent.iter()`` 逐个 yield 图节点，``End`` 即“有结果”。
本模块让调用方 ``async for`` 消费事件，并在 run 结束时拿到最终结果；异常（含工具失败）
照常从生成器抛出，由调用方统一记录遥测。

per_run_step=False 的 DynamicToolset 在 for_run 时只求值一次工具集，scope 的工具类别在
单次对话中不变，这正确且省 DB 查询（见 ai-tools-skill-persona-plan.md）。
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from typing import Any

from pydantic_ai import Agent
from pydantic_ai.messages import ModelMessage
from pydantic_ai.run import AgentRunResult
from pydantic_ai.tools import DeferredToolResults
from pydantic_graph import GraphRunContext

from .deps import AgentDeps


@dataclass(frozen=True, slots=True)
class RunEvent:
    """run 迭代期间的一个事件。``result`` 非 None 表示 run 已结束。"""

    node: Any  # UserPromptNode / ModelRequestNode / CallToolsNode / End(FinalResult)
    ctx: GraphRunContext
    result: AgentRunResult | None = None  # 仅 run 结束时非 None


async def run_agent(
    agent: Agent[AgentDeps, str],
    prompt: str,
    *,
    deps: AgentDeps,
    message_history: Sequence[ModelMessage] | None = None,
    deferred_tool_results: DeferredToolResults | None = None,
    conversation_id: str | None = None,
    output_type=None,
    capabilities: Sequence[Any] | None = None,
) -> AsyncIterator[RunEvent]:
    """把 ``agent.iter`` 包成异步生成器：逐节点 yield 事件，结束时 yield 最终结果。

    ``deferred_tool_results``/``conversation_id`` 供 Task 审批恢复使用：审批决议后以
    原消息历史 + ``DeferredToolResults`` 重新进入 Agent，沿用同一 conversation 关联。
    ``output_type`` 供 Task 结构化输出（TaskOutput）；chat 不传（默认 str）。
    ``capabilities`` 供 Task 注入 harness 的 Planning/StepPersistence（chat 不传，
    与 agent 构造时的 capabilities 合并）。
    """
    async with agent.iter(
        prompt,
        message_history=message_history,
        deps=deps,
        deferred_tool_results=deferred_tool_results,
        conversation_id=conversation_id,
        output_type=output_type,
        capabilities=capabilities,
    ) as agent_run:
        async for node in agent_run:
            yield RunEvent(node=node, ctx=agent_run.ctx)
        yield RunEvent(node=None, ctx=agent_run.ctx, result=agent_run.result)
