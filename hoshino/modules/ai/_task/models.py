"""Task 领域模型与稳定 DTO。

- 状态机见 plan 6.3：``TaskStatus``（Task 层）与 ``TaskRunState``（一次 attempt）。
- ``TaskOutput`` 是 Task 成功的唯一产物，群消息只渲染它；原始历史/工具参数不公开。
- ``TaskContext`` 是可持久化产品运行上下文；``TaskDeps`` 由能力底座的 ``AgentDeps``
  承载（``task`` 字段），这里只定义序列化所需的字段与快照。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel

TaskKind = Literal["research", "plan"]
CreationPolicy = Literal["all", "admin", "superuser"]
ApprovalMode = Literal["auto", "always", "never"]


class TaskStatus(str, Enum):
    created = "created"
    queued = "queued"
    running = "running"
    waiting_approval = "waiting_approval"
    succeeded = "succeeded"
    failed = "failed"
    cancelled = "cancelled"


class TaskRunState(str, Enum):
    queued = "queued"
    running = "running"
    waiting_approval = "waiting_approval"
    retry_wait = "retry_wait"
    interrupted = "interrupted"
    succeeded = "succeeded"
    failed = "failed"
    cancelled = "cancelled"


class ApprovalState(str, Enum):
    pending = "pending"
    approved = "approved"
    denied = "denied"
    expired = "expired"


# ------------------------------------------------------------ TaskOutput


class Finding(BaseModel):
    title: str
    detail: str = ""


class Source(BaseModel):
    url: str
    title: str = ""


class PlanStep(BaseModel):
    title: str
    description: str = ""


class TaskOutput(BaseModel):
    """Task 的稳定结构化输出。字段可为空；成功状态必须通过本 schema 校验。"""

    summary: str = ""
    findings: list[Finding] = field(default_factory=list)
    sources: list[Source] = field(default_factory=list)
    plan: list[PlanStep] = field(default_factory=list)
    unknowns: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    next_steps: list[str] = field(default_factory=list)

    def render_markdown(self) -> str:
        """渲染为群消息 Markdown；仅摘要与受控字段。"""
        lines = [f"### {self.summary or '（无摘要）'}"]
        for f in self.findings:
            lines.append(f"- **{f.title}**：{f.detail}")
        if self.sources:
            lines.append("")
            lines.append("来源：")
            for s in self.sources:
                lines.append(f"- [{s.title or s.url}]({s.url})")
        if self.plan:
            lines.append("")
            lines.append("计划：")
            for i, p in enumerate(self.plan, 1):
                lines.append(f"{i}. {p.title}")
        if self.risks:
            lines.append("")
            lines.append("风险：" + "；".join(self.risks))
        if self.next_steps:
            lines.append("")
            lines.append("下一步：" + "；".join(self.next_steps))
        return "\n".join(lines)


# ------------------------------------------------------------ TaskContext


@dataclass(slots=True)
class CapabilitySnapshot:
    """Task 创建时冻结的能力快照；后续 scope/技能变化只影响新 Task。"""

    persona_id: int | None = None
    persona_version: int = 0
    skill_names: list[str] = field(default_factory=list)
    enabled_categories: list[str] = field(default_factory=list)
    tool_profile: dict[str, int] = field(default_factory=dict)  # tool_id -> version
    workspace_id: int | None = None
    workspace_root: str = ""
    workspace_mode: str = "read_write"
    approval_mode: ApprovalMode = "auto"
    schema_version: int = 1


@dataclass(slots=True)
class TaskContext:
    """一次 TaskRun 的可持久化运行上下文（DTO，可 JSON 序列化）。"""

    task_id: str
    task_run_id: str
    task_kind: str
    scope_key: str
    creator_id: str
    target_json: str
    bot_self_id: str = ""
    adapter_name: str = ""
    provider_id: str = ""
    model: str = ""
    prompt: str = ""
    conversation_id: str = ""
    agent_run_id: str = ""
    workdir: str = ""
    workdir_mode: str = "read_write"
    approval_mode: ApprovalMode = "auto"
    # 冻结的 persona prompt（恢复时不再做三级解析）与权限快照 JSON
    # （PermissionSnapshot 序列化；后台恢复无 live event 时按此复核权限）。
    persona_prompt: str = ""
    permission_json: str = ""
    tool_profile: frozenset[tuple[str, int]] = field(default_factory=frozenset)
    extra: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "task_id": self.task_id,
            "task_run_id": self.task_run_id,
            "task_kind": self.task_kind,
            "scope_key": self.scope_key,
            "creator_id": self.creator_id,
            "target_json": self.target_json,
            "bot_self_id": self.bot_self_id,
            "adapter_name": self.adapter_name,
            "provider_id": self.provider_id,
            "model": self.model,
            "prompt": self.prompt,
            "conversation_id": self.conversation_id,
            "agent_run_id": self.agent_run_id,
            "workdir": self.workdir,
            "workdir_mode": self.workdir_mode,
            "approval_mode": self.approval_mode,
            "persona_prompt": self.persona_prompt,
            "permission_json": self.permission_json,
            "tool_profile": [list(pair) for pair in sorted(self.tool_profile)],
            "extra": self.extra,
        }
        return data

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "TaskContext":
        profile = frozenset(tuple(pair) for pair in data.get("tool_profile", []))
        return cls(
            task_id=data.get("task_id", ""),
            task_run_id=data.get("task_run_id", ""),
            task_kind=data.get("task_kind", "research"),
            scope_key=data.get("scope_key", ""),
            creator_id=data.get("creator_id", ""),
            target_json=data.get("target_json", ""),
            bot_self_id=data.get("bot_self_id", ""),
            adapter_name=data.get("adapter_name", ""),
            provider_id=data.get("provider_id", ""),
            model=data.get("model", ""),
            prompt=data.get("prompt", ""),
            conversation_id=data.get("conversation_id", ""),
            agent_run_id=data.get("agent_run_id", ""),
            workdir=data.get("workdir", ""),
            workdir_mode=data.get("workdir_mode", "read_write"),
            approval_mode=data.get("approval_mode", "auto"),
            persona_prompt=data.get("persona_prompt", ""),
            permission_json=data.get("permission_json", ""),
            tool_profile=profile,
            extra=data.get("extra", {}),
        )
