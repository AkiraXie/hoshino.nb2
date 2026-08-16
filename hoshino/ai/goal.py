"""跨轮持续目标（GoalService）：每 scope 单目标 + revision CAS + round cap。

对齐 dsh 的 goal 语义（phase=active/paused/blocked/complete + revision CAS +
maxGoalRounds），但用「状态行 + CAS」而非事件溯源（v1；``goal/change`` 事件溯源
留到后续，CAS 已提供 dsh fold 的安全保证，对聊天机器人足够）。

目标**不自动驱动执行**：执行仍由用户逐轮 ``#`` 提问驱动，Goal 只是可显式管理的
跨轮状态；把 Goal 接到 Task/自动续跑留待后续。每 scope 单目标，
``scope_key`` 主键即约束。

本模块不 ``import nonebot``，不作为插件加载。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from . import store

GoalPhase = Literal["active", "paused", "blocked", "complete"]

_PHASE_SET: frozenset[str] = frozenset({"active", "paused", "blocked", "complete"})


@dataclass(frozen=True, slots=True)
class Goal:
    scope_key: str
    objective: str
    phase: GoalPhase
    revision: int
    max_rounds: int | None = None
    completed_rounds: int = 0
    blocked_reason: str = ""


@dataclass(frozen=True, slots=True)
class GoalRef:
    """CAS 引用：scope_key + 当前 revision；不匹配抛 ``GoalConflict``。"""

    scope_key: str
    revision: int


class GoalConflict(RuntimeError):  # noqa: N818  # 命名与 dsh 的 GoalConflict 对齐，刻意不加 Error 后缀
    """revision CAS 冲突：目标已被并发修改，调用方需重读重试。"""


def _from_row(scope_key: str, row: dict) -> Goal:
    return Goal(
        scope_key=scope_key,
        objective=row["objective"],
        phase=row["phase"],  # type: ignore[arg-type]  # DB 值已由写入方约束
        revision=row["revision"],
        max_rounds=row["max_rounds"],
        completed_rounds=row["completed_rounds"],
        blocked_reason=row["blocked_reason"],
    )


class GoalService:
    """每 scope 单目标的显式状态机（进程内无缓存，读写直连 store）。"""

    def create(self, scope_key: str, objective: str, max_rounds: int | None = None) -> Goal:
        """创建或替换目标（revision 重置为 1）。"""
        objective = objective.strip()
        if not objective:
            raise ValueError("目标不能为空。")
        goal = Goal(
            scope_key=scope_key,
            objective=objective,
            phase="active",
            revision=1,
            max_rounds=max_rounds,
        )
        self._write(goal)
        return goal

    def get(self, scope_key: str) -> Goal | None:
        row = store.get_goal(scope_key)
        return _from_row(scope_key, row) if row is not None else None

    def update(
        self,
        scope_key: str,
        ref: GoalRef,
        action: str,
        *,
        objective: str | None = None,
        blocked_reason: str | None = None,
    ) -> Goal:
        """按 action 迁移目标状态；``ref`` revision 必须匹配当前值，否则抛 GoalConflict。

        action：edit | pause | resume | complete | blocked | advance_round。
        """
        goal = self.get(scope_key)
        if goal is None:
            raise GoalConflict("目标不存在。")
        if ref.revision != goal.revision:
            raise GoalConflict("目标已变化，请重新查看后重试。")

        phase: str = goal.phase
        completed_rounds = goal.completed_rounds
        new_objective = goal.objective
        new_blocked_reason = goal.blocked_reason

        match action:
            case "edit":
                if objective is None or not objective.strip():
                    raise ValueError("目标不能为空。")
                new_objective = objective.strip()
            case "pause":
                phase = "paused"
            case "resume":
                phase = "active"
            case "complete":
                phase = "complete"
            case "blocked":
                if not blocked_reason or not blocked_reason.strip():
                    raise ValueError("blocked 必须给出阻塞原因。")
                phase = "blocked"
                new_blocked_reason = blocked_reason.strip()
            case "advance_round":
                if phase in ("complete", "blocked"):
                    return goal  # 终态不再推进轮次
                completed_rounds += 1
                if goal.max_rounds is not None and completed_rounds >= goal.max_rounds:
                    phase = "complete"
            case _:
                raise ValueError(f"未知 goal action：{action}")

        new = Goal(
            scope_key=scope_key,
            objective=new_objective,
            phase=phase,  # type: ignore[arg-type]
            revision=goal.revision + 1,
            max_rounds=goal.max_rounds,
            completed_rounds=completed_rounds,
            blocked_reason=new_blocked_reason,
        )
        self._write(new)
        return new

    def clear(self, scope_key: str) -> bool:
        return store.delete_goal(scope_key)

    @staticmethod
    def _write(goal: Goal) -> None:
        store.upsert_goal(
            goal.scope_key,
            objective=goal.objective,
            phase=goal.phase,
            revision=goal.revision,
            max_rounds=goal.max_rounds,
            completed_rounds=goal.completed_rounds,
            blocked_reason=goal.blocked_reason,
        )
