"""通用 Agent runner：在当前任务内完整驱动一次 ``agent.iter()`` run 并返回结果。

pydantic-ai 的一次 run 是循环图（UserPromptNode → ModelRequestNode → CallToolsNode →
… → End(FinalResult)）。本模块在 ``async with agent.iter(...)`` 内把图跑到结束，
再返回最终结果；异常（含工具失败）照常抛出，由调用方统一记录遥测。

注意：``agent.iter`` 上下文内部由 pydantic_graph 管理 anyio task group / cancel scope，
enter 与 exit 必须发生在同一个任务。因此不要把 run 循环以异步生成器形式暴露给调用方：
调用方提前 break/return 会把迭代器悬空在 ``async with`` 内，scope 退出被推迟到
asyncgen GC finalizer，泄漏在 matcher 任务的 scope 栈上，导致 NoneBot 的 shield
CancelScope 退出时报 "Attempted to exit a cancel scope that isn't the current
tasks's current cancel scope"。

per_run_step=False 的 DynamicToolset 在 for_run 时只求值一次工具集，scope 的工具类别在
单次对话中不变，这正确且省 DB 查询（见 ai-tools-skill-persona-plan.md）。
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from pydantic_ai import Agent
from pydantic_ai.messages import ModelMessage
from pydantic_ai.run import AgentRunResult
from pydantic_ai.tools import DeferredToolResults
from pydantic_ai.usage import UsageLimits
from pydantic_graph import GraphRunContext

from ._deps import AgentDeps


@dataclass(frozen=True, slots=True)
class RunEvent:
    """run 迭代期间的一个图节点事件。"""

    node: Any  # UserPromptNode / ModelRequestNode / CallToolsNode / …
    ctx: GraphRunContext


def tool_calls_from_node(node: Any) -> list[str]:
    """从图节点提取本步发起的工具调用名（duck-typed，容忍 pydantic-ai 版本差异）。

    供失败日志标注“失败前调用过哪些工具”（如 web_search），帮助定位是模型
    侧问题还是工具侧问题。非 ``CallToolsNode`` 或解析失败一律返回空列表。
    """
    if type(node).__name__ != "CallToolsNode":
        return []
    response = getattr(node, "model_response", None)
    parts = getattr(response, "parts", None) or []
    names: list[str] = []
    for part in parts:
        name = getattr(part, "tool_name", None)
        if name:
            names.append(str(name))
    return names


async def run_agent(
    agent: Agent[AgentDeps, Any],
    prompt: str,
    *,
    deps: AgentDeps,
    message_history: Sequence[ModelMessage] | None = None,
    deferred_tool_results: DeferredToolResults | None = None,
    conversation_id: str | None = None,
    output_type=None,
    capabilities: Sequence[Any] | None = None,
    on_event: Callable[[RunEvent], None] | None = None,
    usage_limits: UsageLimits | None = None,
) -> AgentRunResult | None:
    """驱动 Agent run 直到结束，返回最终结果（未正常结束时为 None）。

    ``on_event``：可选同步回调，每个图节点触发一次，供 heartbeat / 取消检查。
    ``deferred_tool_results``/``conversation_id`` 供 Task 审批恢复使用：审批决议后以
    原消息历史 + ``DeferredToolResults`` 重新进入 Agent，沿用同一 conversation 关联。
    ``output_type`` 供 Task 结构化输出（TaskOutput）；chat 不传（默认 str）。
    ``capabilities`` 供 Task 注入 harness 的 Planning/StepPersistence（chat 不传，
    与 agent 构造时的 capabilities 合并）。
    ``usage_limits``：run 级护栏（请求次数/token 上限，超限抛 UsageLimitExceeded）；
    持久化不能替代超时，见 aichat-context-timeout-plan.md §3。
    """
    async with agent.iter(
        prompt,
        message_history=message_history,
        deps=deps,
        deferred_tool_results=deferred_tool_results,
        conversation_id=conversation_id,
        output_type=output_type,
        capabilities=capabilities,
        usage_limits=usage_limits,
    ) as agent_run:
        async for node in agent_run:
            if on_event is not None:
                on_event(RunEvent(node=node, ctx=agent_run.ctx))
        return agent_run.result
