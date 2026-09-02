"""Pydantic AI Harness 兼容 facade。

选择性引入官方 ``pydantic-ai-harness`` 的 **Planning** / **StepPersistence** 能力：

- ``Planning``：结构化计划工具（``add_task``/``update_task_status``/``read_plan`` 等）。
  计划按 ``ctx.deps.task.task_id`` 落到与 task store 同一 SQLite 文件的独立
  ``session``（``SqlitePlanStore``），一个 Task 的计划跨 attempt/恢复持久且彼此隔离。
- ``StepPersistence``：step 事件 ledger + tool-effect ledger + 可续跑 snapshot。
  ``agent_name`` 传 Task id，capability 自动派生 ``{task_id}-{suffix}`` 的独立 run_id。
- ``Skills``：harness 的 ``Skills(directories, ...)`` 能力仅作为可选扩展暴露；v1 的
  Task surface **不**默认注入它——Task 创建时 Skill archive 已按内容冻结进 ``tool_profile``，
  与能力底座的 ``skill_read`` 工具由同一 registry 展开，再叠加 harness Skills 会造成
  工具重复。

**降级路径**：harness 为独立 0.x 包，import 失败或版本不满足时，模块级 ``_HARNESS_AVAILABLE``
为 False，所有构建函数返回 ``None`` / 空列表，Task runtime 照常工作（无 planning 工具、
无 step ledger）。StepPersistence 默认用进程内 ``InMemoryStepStore``；跨进程 Task 恢复仍由
``TaskContext.message_history_json`` 承担（v1 明确不做完整 graph-state checkpoint）。
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from . import store as ai_store

try:
    from pydantic_ai_harness.planning import (
        InMemoryPlanStore,
        PlanStore,
        SqlitePlanStore,
    )
    from pydantic_ai_harness.planning import (
        Planning as _HarnessPlanning,
    )
    from pydantic_ai_harness.skills import Skills as _HarnessSkills
    from pydantic_ai_harness.step_persistence import (
        InMemoryStepStore,
    )
    from pydantic_ai_harness.step_persistence import (
        StepPersistence as _HarnessStepPersistence,
    )

    _HARNESS_AVAILABLE = True
except ImportError:  # pragma: no cover - 降级路径，按 __all__ 之外不可达
    InMemoryPlanStore = None  # type: ignore[assignment,misc]
    PlanStore = None  # type: ignore[assignment,misc]
    SqlitePlanStore = None  # type: ignore[assignment,misc]
    InMemoryStepStore = None  # type: ignore[assignment,misc]
    _HarnessPlanning = None  # type: ignore[assignment]
    _HarnessStepPersistence = None  # type: ignore[assignment]
    _HarnessSkills = None  # type: ignore[assignment]
    _HARNESS_AVAILABLE = False


def harness_available() -> bool:
    """harness 是否可用（版本满足且可 import）。"""
    return _HARNESS_AVAILABLE


def _plan_db_path() -> str | None:
    """Task plan 与 task store 共用同一 SQLite 文件（跟随测试 monkeypatch 的 engine）。"""
    database = getattr(ai_store.engine.url, "database", None)
    return database if database else None


def _plan_store_resolver(ctx) -> PlanStore | None:
    """按 ``ctx.deps.task.task_id`` 解析独立的 plan 空间；无 task 时退回内存 store。"""
    task_id = None
    deps = getattr(ctx, "deps", None)
    task = getattr(deps, "task", None) if deps is not None else None
    if task is not None:
        task_id = getattr(task, "task_id", None) or None
    db = _plan_db_path()
    if db:
        return SqlitePlanStore(db, session=task_id or "default")
    # 无引擎路径（纯内存/脚本环境）：SqlitePlanStore 不接受 ":memory:"，回退进程内 store。
    return InMemoryPlanStore()


def build_planning(
    *,
    enable_subtasks: bool = False,
    guidance: str | None = None,
    tools: Sequence[str] | None = None,
) -> Any | None:
    """构建 Planning capability；harness 不可用时返回 None。

    store 由 resolver 按当前 run 的 ``deps.task`` 动态解析，因此同一个 Agent（共享缓存）
    服务多个 Task 时 plan 空间天然隔离，不随 scope/绑定失效。
    """
    if not _HARNESS_AVAILABLE:
        return None
    return _HarnessPlanning(
        guidance=guidance,
        store_resolver=_plan_store_resolver,
        enable_subtasks=enable_subtasks,
        tools=tools,
    )


def build_step_persistence(
    *,
    agent_name: str,
    store: Any | None = None,
) -> Any | None:
    """构建 StepPersistence；harness 不可用时返回 None。

    ``agent_name`` 传 Task id：capability 自动派生 ``{agent_name}-{suffix}`` 的 run_id，
    step/tool-effect ledger 与 snapshot 天然按 Task 隔离。默认 ``InMemoryStepStore``
    （进程内）；自定义后端可传满足 ``StepStore`` 协议的 store。
    """
    if not _HARNESS_AVAILABLE:
        return None
    return _HarnessStepPersistence(
        store=store if store is not None else InMemoryStepStore(),
        agent_name=agent_name,
    )


def build_skills(
    directories: str | Sequence[str],
    *,
    include: Sequence[str] | None = None,
) -> Any | None:
    """构建 harness ``Skills`` capability（可选扩展）；harness 不可用时返回 None。

    v1 Task surface 不默认注入（skill 已冻结进 tool_profile），该函数供后续按 scope
    能力 profile 显式开启。
    """
    if not _HARNESS_AVAILABLE:
        return None
    return _HarnessSkills(directories, include=include)


def build_task_capabilities(
    *,
    task_id: str,
    enable_planning: bool = True,
    enable_step: bool = True,
) -> list[Any]:
    """Task run 的 capability 集合；harness 不可用时为空列表（降级，功能不缺失）。"""
    caps: list[Any] = []
    if enable_planning:
        planning = build_planning(enable_subtasks=True)
        if planning is not None:
            caps.append(planning)
    if enable_step:
        step = build_step_persistence(agent_name=task_id)
        if step is not None:
            caps.append(step)
    return caps
