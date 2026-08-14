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
单次对话中不变，这正确且省 DB 查询。
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from pydantic_ai import Agent
from pydantic_ai.exceptions import UsageLimitExceeded
from pydantic_ai.messages import ModelMessage, UserContent
from pydantic_ai.run import AgentRunResult
from pydantic_ai.tools import DeferredToolResults
from pydantic_ai.usage import UsageLimits
from pydantic_graph import GraphRunContext

from . import hooks
from .deps import AgentDeps


@dataclass(frozen=True, slots=True)
class RunEvent:
    """run 迭代期间的一个图节点事件。"""

    node: Any  # UserPromptNode / ModelRequestNode / CallToolsNode / …
    ctx: GraphRunContext


@dataclass(slots=True)
class RunLog:
    """一次 turn 的进程内观测收集（可观测/审计，非持久化对象）。

    ``run_agent`` 在迭代图节点时填充 steps / step_at / tool_calls / nodes；
    started_at 在首次进入时设置（跨 retry 尝试不重置），ended_at / reason 在
    退出或异常时设置。``reason`` 取值：completed | error | timeout |
    max-requests | aborted。

    ``nodes`` 是节点级轨迹（观测日志用）：按执行顺序记录
    ``{type: model_request|tools|end, ts, detail}``。model_request 的 detail
    为上一动作摘要（用户提问 / 工具结果 / 重试）；tools 的 detail 为
    ``{calls, introspection}``（脱敏参数 + 模型思考/中间文本摘要）。
    """

    started_at: float = 0.0
    ended_at: float = 0.0
    steps: int = 0
    step_at: list[float] = field(default_factory=list)  # 每个 model request 完成时刻
    tool_calls: list[dict] = field(default_factory=list)  # {name, args_summary}
    reason: str = ""
    nodes: list[dict] = field(default_factory=list)


def summarize_content(content: Any, limit: int = 200) -> str:
    """把消息部件内容压缩成日志摘要：文本截断、二进制标类型/大小、列表逐项。"""
    if content is None:
        return ""
    if isinstance(content, str):
        return content if len(content) <= limit else content[:limit] + "…"
    if isinstance(content, bytes):
        return f"<bytes:{len(content)}>"
    if isinstance(content, list):
        joined = " | ".join(summarize_content(item, limit) for item in content)
        return joined if len(joined) <= limit else joined[:limit] + "…"
    data = getattr(content, "data", None)
    media_type = getattr(content, "media_type", None)
    if isinstance(data, bytes):
        return f"<{media_type or 'binary'}:{len(data)}B>"
    text = str(content)
    return text if len(text) <= limit else text[:limit] + "…"


def _last_message_summary(state: Any) -> str:
    """从 AgentState.message_history 尾部提取上一步产生的消息摘要。

    duck-typed 容忍版本差异；提取 UserPromptPart（首轮提问）/ ToolReturnPart
    （工具结果）/ RetryPromptPart（重试），其余部件跳过。
    """
    history = getattr(state, "message_history", None) or []
    if not history:
        return ""
    pieces: list[str] = []
    for part in getattr(history[-1], "parts", None) or []:
        name = type(part).__name__
        if name == "UserPromptPart":
            pieces.append(
                f"user: {summarize_content(getattr(part, 'content', None), 120)}"
            )
        elif name == "ToolReturnPart":
            tool = getattr(part, "tool_name", "")
            pieces.append(
                f"tool {tool} → {summarize_content(getattr(part, 'content', None), 160)}"
            )
        elif name == "RetryPromptPart":
            pieces.append(
                f"retry: {summarize_content(getattr(part, 'content', None), 120)}"
            )
    return " ｜ ".join(pieces)


def _response_introspection(node: Any) -> str:
    """提取 CallToolsNode 的 model_response 中思考/中间文本摘要（观测用）。"""
    response = getattr(node, "model_response", None)
    parts = getattr(response, "parts", None) or []
    pieces: list[str] = []
    for part in parts:
        if type(part).__name__ in ("ThinkingPart", "TextPart"):
            content = getattr(part, "content", None)
            if content:
                pieces.append(summarize_content(content, 120))
    return " ｜ ".join(pieces)


def redact_args(args: Any) -> str:
    """把工具参数脱敏为「键名 + 值长度」摘要，不落完整参数（供 tool/call 事件）。

    与 ``task/scheduler._params_summary`` 同语义；此处单独实现以规避
    scheduler → runtime → runner 的循环 import（未来可抽公共 util 合并）。
    """
    if args is None:
        return "{}"
    if isinstance(args, str):
        return f"<str:{len(args)}>"
    if isinstance(args, dict):
        parts = []
        for key, value in args.items():
            if isinstance(value, (str, bytes)):
                parts.append(f"{key}=<{len(value)}>")
            else:
                parts.append(f"{key}={type(value).__name__}")
        return "{" + ", ".join(parts) + "}"
    return type(args).__name__


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


def tool_call_events_from_node(node: Any) -> list[dict]:
    """从图节点提取本步发起的工具调用事件（name + 脱敏参数摘要）。

    与 ``tool_calls_from_node`` 同 duck-typed 识别；额外取 ``part.args`` 做脱敏，
    供 ``RunLog.tool_calls`` 落 ``tool/call`` 事件。非 ``CallToolsNode`` 或解析
    失败返回空列表。
    """
    if type(node).__name__ != "CallToolsNode":
        return []
    response = getattr(node, "model_response", None)
    parts = getattr(response, "parts", None) or []
    events: list[dict] = []
    for part in parts:
        name = getattr(part, "tool_name", None)
        if name:
            events.append(
                {
                    "name": str(name),
                    "args_summary": redact_args(getattr(part, "args", None)),
                }
            )
    return events


def describe_node(node: Any, ctx: GraphRunContext) -> str | None:
    """把单个图节点转成实时日志描述；无内容的节点返回 None。

    供 chat 的实时日志回调使用（每步即时打印，不再攒到最后）：
    - ModelRequestNode → 上一步动作摘要（用户提问 / 工具结果 / 重试）；
    - CallToolsNode → 本步发起的工具调用清单（脱敏参数）。
    """
    name = type(node).__name__
    if name == "ModelRequestNode":
        state = getattr(ctx, "state", None)
        detail = _last_message_summary(state)
        return f"model_request · {detail}" if detail else "model_request"
    if name == "CallToolsNode":
        calls = tool_call_events_from_node(node)
        if not calls:
            return None
        joined = " | ".join(f"{c['name']}{c['args_summary']}" for c in calls)
        return f"tools · {joined}"
    return None


async def run_agent(
    agent: Agent[AgentDeps, Any],
    prompt: UserContent | None,
    *,
    deps: AgentDeps,
    message_history: Sequence[ModelMessage] | None = None,
    deferred_tool_results: DeferredToolResults | None = None,
    conversation_id: str | None = None,
    output_type=None,
    capabilities: Sequence[Any] | None = None,
    on_event: Callable[[RunEvent], None] | None = None,
    usage_limits: UsageLimits | None = None,
    run_log: RunLog | None = None,
) -> AgentRunResult | None:
    """驱动 Agent run 直到结束，返回最终结果（未正常结束时为 None）。

    ``prompt``：文本或多模态 UserContent 序列（chat 含图时传 ``[TextContent, ImageUrl/...]``）。
    ``on_event``：可选同步回调，每个图节点触发一次，供 heartbeat / 取消检查。
    ``deferred_tool_results``/``conversation_id`` 供 Task 审批恢复使用：审批决议后以
    原消息历史 + ``DeferredToolResults`` 重新进入 Agent，沿用同一 conversation 关联。
    ``output_type`` 供 Task 结构化输出（TaskOutput）；chat 不传（默认 str）。
    ``capabilities`` 供 Task 注入 harness 的 Planning/StepPersistence（chat 不传，
    与 agent 构造时的 capabilities 合并）。
    ``usage_limits``：run 级护栏（请求次数/token 上限，超限抛 UsageLimitExceeded）；
    持久化不能替代超时。
    ``run_log``：可选进程内观测收集器；填充 started_at/steps/tool_calls/ended_at/
    reason。chat 用它落 log-only 事件与失败日志的 tools 字段；task 不传。
    """
    if run_log is not None and run_log.started_at == 0.0:
        run_log.started_at = time.time()

    def _observe(node: Any, ctx: GraphRunContext) -> None:
        if run_log is not None:
            now = time.time()
            name = type(node).__name__
            if name == "ModelRequestNode":
                run_log.steps += 1
                run_log.step_at.append(now)
                # GraphRunContext.state 可能缺失（测试替身），duck-typed 容错。
                state = getattr(ctx, "state", None)
                run_log.nodes.append(
                    {
                        "type": "model_request",
                        "ts": now,
                        "detail": _last_message_summary(state),
                    }
                )
            elif name == "CallToolsNode":
                calls = tool_call_events_from_node(node)
                run_log.tool_calls.extend(calls)
                run_log.nodes.append(
                    {
                        "type": "tools",
                        "ts": now,
                        "detail": {
                            "calls": calls,
                            "introspection": _response_introspection(node),
                        },
                    }
                )
            elif name == "End":
                run_log.nodes.append({"type": "end", "ts": now})
        if on_event is not None:
            on_event(RunEvent(node=node, ctx=ctx))

    try:
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
                _observe(node, agent_run.ctx)
            if run_log is not None:
                run_log.reason = "completed"
                run_log.ended_at = time.time()
            return agent_run.result
    except BaseException:
        if run_log is not None:
            run_log.ended_at = time.time()
        raise


def is_transient_error(exc: Exception) -> bool:
    """判定瞬态 provider 异常：可安全重试的第一次模型请求失败。

    只覆盖限流（429）与服务端 5xx / 传输层错误 / 连接错误；不覆盖护栏异常
    （``TimeoutError``/``UsageLimitExceeded``，由调用方在重试前排除）。
    """
    from httpx import TransportError
    from pydantic_ai.exceptions import ModelHTTPError

    if isinstance(exc, ModelHTTPError):
        status = getattr(exc, "status_code", None)
        return status == 429 or (isinstance(status, int) and status >= 500)
    if isinstance(exc, TransportError):
        return True
    return isinstance(exc, ConnectionError)


async def run_agent_with_retry(
    agent: Agent[AgentDeps, Any],
    prompt: UserContent | None,
    *,
    deps: AgentDeps,
    message_history: Sequence[ModelMessage] | None = None,
    deferred_tool_results: DeferredToolResults | None = None,
    conversation_id: str | None = None,
    output_type=None,
    capabilities: Sequence[Any] | None = None,
    on_event: Callable[[RunEvent], None] | None = None,
    usage_limits: UsageLimits | None = None,
    run_log: RunLog | None = None,
    max_retries: int = 2,
) -> AgentRunResult | None:
    """带 request-error 有界重试的 ``run_agent``。

    ``prompt`` 同 ``run_agent``（支持多模态 UserContent 序列）。
    重试仅在同时满足：异常被 hook 判定 retry 或落入内置瞬态分类器、且本次 turn
    尚无工具调用（无副作用，重进 ``agent.iter`` 不会重放工具执行）、且未达上限。
    护栏异常（``TimeoutError``/``UsageLimitExceeded``）不重试，直接抛出。
    """
    attempt = 0
    while True:
        try:
            return await run_agent(
                agent,
                prompt,
                deps=deps,
                message_history=message_history,
                deferred_tool_results=deferred_tool_results,
                conversation_id=conversation_id,
                output_type=output_type,
                capabilities=capabilities,
                on_event=on_event,
                usage_limits=usage_limits,
                run_log=run_log,
            )
        except (TimeoutError, UsageLimitExceeded):
            raise
        except Exception as exc:
            attempt += 1
            ctx = hooks.RequestErrorContext(
                exc=exc,
                scope_key=deps.scope_key,
                provider_id=deps.telemetry.provider_id,
                surface=deps.surface,
                attempt=attempt,
                deps=deps,
            )
            decision = hooks.run_request_error_hooks(ctx)
            no_side_effects = run_log is None or not run_log.tool_calls
            if (
                (decision.retry or is_transient_error(exc))
                and no_side_effects
                and attempt <= max_retries
            ):
                continue
            raise
