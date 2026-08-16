"""TaskRun -> AgentRun：把持久化 TaskContext 转成一次 Pydantic Agent run。

复用能力底座的 ``AgentDeps``/``providers``/``runner``：surface="task"，工具按冻结
``tool_profile`` 展开，persona 用冻结 ``persona_prompt``。每次 run 结束把 message
history 序列化写回 TaskContext（审批恢复/重启恢复用），不读 ``#`` 聊天的会话历史。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from pydantic_ai.tools import DeferredToolRequests

from .. import (
    context,
    harness,
    hooks,
    provider,
    providers,
    runner,
)
from ..deps import AgentDeps, PermissionSnapshot, Telemetry
from .models import TaskContext, TaskOutput


class TaskRuntimeError(RuntimeError):
    """Task 执行期间的确定性错误（provider 缺失、run 无结果等）。"""


@dataclass(slots=True)
class RunOutcome:
    """一次 Agent run 的产物（进程内使用；持久状态由 scheduler 落库）。"""

    agent_run_id: str
    conversation_id: str
    messages_json: str
    output: Any  # TaskOutput | DeferredToolRequests | None
    result: Any = None  # AgentRunResult，供 telemetry/消息序列化
    usage: dict[str, Any] = field(default_factory=dict)

    @property
    def deferred(self) -> bool:
        return isinstance(self.output, DeferredToolRequests)


def permission_from_json(permission_json: str) -> PermissionSnapshot:
    """反序列化冻结的权限快照；缺省或解析失败时按无权限处理（不因旧快照放宽）。"""
    if not permission_json:
        return PermissionSnapshot()
    try:
        data = json.loads(permission_json)
    except (ValueError, TypeError):
        return PermissionSnapshot()
    return PermissionSnapshot(
        user_id=data.get("user_id"),
        is_superuser=bool(data.get("is_superuser", False)),
        is_admin=bool(data.get("is_admin", False)),
    )


def permission_to_json(permissions: PermissionSnapshot) -> str:
    return json.dumps(
        {
            "user_id": permissions.user_id,
            "is_superuser": permissions.is_superuser,
            "is_admin": permissions.is_admin,
        },
        ensure_ascii=False,
    )


def build_task_deps(ctx: TaskContext, config) -> AgentDeps:
    """构造 Task surface 的 AgentDeps。bot/event 恒为 None（后台运行）。"""
    from hoshino.platform.target import load_target

    return AgentDeps(
        surface="task",
        scope_key=ctx.scope_key,
        target=load_target(ctx.target_json),
        config=config,
        permissions=permission_from_json(ctx.permission_json),
        bot=None,
        event=None,
        telemetry=Telemetry(
            provider_id=ctx.provider_id,
            scope_key=ctx.scope_key,
            model=ctx.model,
        ),
        task=ctx,
    )


async def run_task_run(
    ctx: TaskContext,
    config,
    *,
    deferred=None,
    on_event=None,
) -> RunOutcome:
    """执行一次 Agent run，返回结构化产物。

    ``deferred``：审批恢复时传 ``DeferredToolResults``；
    ``on_event``：可选同步回调，scheduler 用于 heartbeat / 取消检查。
    """
    record = provider.get_provider(ctx.provider_id)
    if record is None:
        raise TaskRuntimeError(f"provider {ctx.provider_id} 不存在")
    agent = providers.build_agent(
        ctx.provider_id,
        record,
        ctx.model,
        proxy=provider.resolve_effective_proxy(record, config.proxy),
        tool_max_retries=config.tool_max_retries,
    )
    deps = build_task_deps(ctx, config)
    history = context.deserialize_messages(ctx.extra.get("message_history_json"))
    # harness 可用时注入 Planning + StepPersistence；不可用时为空列表（降级，功能不缺失）。
    capabilities = harness.build_task_capabilities(task_id=ctx.task_id)

    # pre-step 瀑布：task 的 reject 表现为确定性错误，交 scheduler 既有失败流程承接。
    pre = hooks.run_pre_step_hooks(
        hooks.PreStepContext(
            prompt=ctx.prompt,
            history=history,
            scope_key=ctx.scope_key,
            provider_id=ctx.provider_id,
            surface="task",
            deps=deps,
        )
    )
    if pre.action == "reject":
        raise TaskRuntimeError(pre.reply or "pre_step_reject")
    prompt = pre.prompt if pre.action == "rewrite" and pre.prompt is not None else ctx.prompt

    run_log = runner.RunLog()
    result = await runner.run_agent_with_retry(
        agent,
        prompt,
        deps=deps,
        message_history=history,
        deferred_tool_results=deferred,
        conversation_id=ctx.conversation_id or None,
        output_type=TaskOutput,
        capabilities=capabilities,
        on_event=on_event,
        run_log=run_log,
    )
    if result is None:
        raise TaskRuntimeError("Agent run 未返回结果")

    usage = getattr(result, "usage", None)
    return RunOutcome(
        agent_run_id=result.run_id,
        conversation_id=result.conversation_id,
        messages_json=context.serialize_messages(list(result.all_messages())),
        output=result.output,
        result=result,
        usage={
            "requests": getattr(usage, "requests", 0),
            "request_tokens": getattr(usage, "request_tokens", 0),
            "response_tokens": getattr(usage, "response_tokens", 0),
            "total_tokens": getattr(usage, "total_tokens", 0),
        },
    )
