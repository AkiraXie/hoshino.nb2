"""AI run 拦截瀑布（chat 语义）：pre-step / request-error / post-execute 接缝。

对齐 dsh 的 ``agent/pre-step``（reject | enter）与 ``agent/request-error``
（retry）语义，但落在**模型可见**层而非表面编辑层：

- pre-step 只改写进入模型的 ``prompt``，不改已持久化的历史（聊天平台无法
  "撤回/修改" 已发消息，模型可见改写与表面不可变互不冲突）；
- request-error 只对瞬态 provider 异常做有界重试，且仅在尚无工具副作用时；
- post-execute 本期只定义接缝（注册表 + 决策类型），不接线（归 Phase 3 工具管线，
  且它不能回滚工具副作用，只能门控"模型下一步看到什么"）。

hook 均为同步纯函数（决策只依赖上下文，不做 I/O）；有序注册表，短路语义。
本模块不 ``import nonebot``，不作为插件加载。
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from pydantic_ai.messages import ModelMessage

from ._deps import AgentDeps


# ------------------------------------------------------------ 决策类型


@dataclass(slots=True)
class PreStepDecision:
    """pre-step 决策：accept（放行）/ reject（拒绝本轮）/ rewrite（改写 prompt）。"""

    action: str = "accept"  # accept | reject | rewrite
    reply: str = ""  # reject 时的用户可见文案
    prompt: str | None = None  # rewrite 时替换后的 prompt

    @classmethod
    def accept(cls) -> "PreStepDecision":
        return cls()

    @classmethod
    def reject(cls, reply: str) -> "PreStepDecision":
        return cls(action="reject", reply=reply)

    @classmethod
    def rewrite(cls, prompt: str) -> "PreStepDecision":
        return cls(action="rewrite", prompt=prompt)


@dataclass(slots=True)
class RequestErrorDecision:
    """request-error 决策：retry=True 表示有界重试（仍受"无副作用"守卫与上限约束）。"""

    retry: bool = False

    @classmethod
    def fail(cls) -> "RequestErrorDecision":
        return cls()

    @classmethod
    def retry_once(cls) -> "RequestErrorDecision":
        return cls(retry=True)


@dataclass(slots=True)
class PostExecuteDecision:
    """post-execute 决策（预留缝，本期不接线）：accept / replace / block。"""

    action: str = "accept"  # accept | replace | block
    result: Any = None  # replace 时替换后的结果
    reason: str = ""  # block 时的原因


# ------------------------------------------------------------ 上下文


@dataclass(slots=True)
class PreStepContext:
    prompt: str
    history: Sequence[ModelMessage]
    scope_key: str | None
    provider_id: str
    surface: str
    deps: AgentDeps


@dataclass(slots=True)
class RequestErrorContext:
    exc: Exception
    scope_key: str | None
    provider_id: str
    surface: str
    attempt: int  # 从 1 计
    deps: AgentDeps


@dataclass(slots=True)
class PostExecuteContext:
    tool_name: str
    args: dict
    result: Any
    deps: AgentDeps


# ------------------------------------------------------------ 注册表

PreStepHook = Callable[[PreStepContext], PreStepDecision | None]
RequestErrorHook = Callable[[RequestErrorContext], RequestErrorDecision | None]
PostExecuteHook = Callable[[PostExecuteContext], PostExecuteDecision | None]

PRE_STEP_HOOKS: list[PreStepHook] = []
REQUEST_ERROR_HOOKS: list[RequestErrorHook] = []
POST_EXECUTE_HOOKS: list[PostExecuteHook] = []


def register_pre_step(fn: PreStepHook) -> PreStepHook:
    PRE_STEP_HOOKS.append(fn)
    return fn


def register_request_error(fn: RequestErrorHook) -> RequestErrorHook:
    REQUEST_ERROR_HOOKS.append(fn)
    return fn


def register_post_execute(fn: PostExecuteHook) -> PostExecuteHook:
    POST_EXECUTE_HOOKS.append(fn)
    return fn


def reset_hooks() -> None:
    """清空全部注册表（测试隔离用）。"""
    PRE_STEP_HOOKS.clear()
    REQUEST_ERROR_HOOKS.clear()
    POST_EXECUTE_HOOKS.clear()


# ------------------------------------------------------------ 执行（waterfall）


def run_pre_step_hooks(ctx: PreStepContext) -> PreStepDecision:
    """首个非 accept 决策即短路；无订阅者/全部 accept 时返回 accept。"""
    for hook in PRE_STEP_HOOKS:
        decision = hook(ctx)
        if decision is not None and decision.action != "accept":
            return decision
    return PreStepDecision.accept()


def run_request_error_hooks(ctx: RequestErrorContext) -> RequestErrorDecision:
    """首个显式 retry 决策即短路；否则默认 fail（不重试）。"""
    for hook in REQUEST_ERROR_HOOKS:
        decision = hook(ctx)
        if decision is not None and decision.retry:
            return decision
    return RequestErrorDecision.fail()


def run_post_execute_hooks(ctx: PostExecuteContext) -> PostExecuteDecision:
    """预留缝：本期无接线，恒 accept。"""
    for hook in POST_EXECUTE_HOOKS:
        decision = hook(ctx)
        if decision is not None and decision.action != "accept":
            return decision
    return PostExecuteDecision()
