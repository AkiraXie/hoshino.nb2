"""WorkerSpec：Agent 角色与模型/工具/预算配置。

v1 只注册 ``general``，不建 planner/researcher/reviewer 等固定角色分支。
Task 创建时把 scope persona、Skill archive、category binding 展开的 tool profile、
approval mode 和 workspace 冻结进 capability snapshot；WorkerSpec 只携带常量级配置。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class WorkerSpec:
    kind: str = "general"
    system_instructions: str = ""
    usage_limits: dict[str, Any] = field(default_factory=dict)


GENERAL_WORKER = WorkerSpec()
