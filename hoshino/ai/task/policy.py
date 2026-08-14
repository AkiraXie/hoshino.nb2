"""scope task policy、cooldown、并发 guard 与 workspace 冻结。

检查顺序：Service 启用 → scope policy → 用户实际权限 → 并发上限 → cooldown。
cooldown 只在创建事务内原子判定（``store.create_task``），这里提供窗口内最近 Task
的查询用于提前提示，不承担唯一判定职责。
"""

from __future__ import annotations

import time
from typing import Any

from . import store as task_store

COOLDOWN_WINDOW = 300.0


def get_creation_policy(scope_key: str) -> str:
    """新 scope 默认 superuser；只有 SUPERUSER 可修改。"""
    return task_store.get_scope_policy(scope_key)["creation_policy"]


def policy_allows_creation(policy: str, *, is_superuser: bool, is_admin: bool) -> bool:
    if policy == "all":
        return True
    if policy == "admin":
        return is_admin or is_superuser
    return is_superuser


def check_concurrent(scope_key: str) -> tuple[bool, int, int]:
    """并发 guard：返回 (允许, 当前活跃数, 上限)。max_concurrent<=0 表示不限制。"""
    max_concurrent = task_store.get_scope_policy(scope_key)["max_concurrent"]
    active = task_store.count_active_runs(scope_key)
    if max_concurrent and active >= max_concurrent:
        return False, active, max_concurrent
    return True, active, max_concurrent


def cooldown_status(
    scope_key: str, creator_id: str, now: float | None = None
) -> dict[str, Any] | None:
    """窗口内最近 Task 信息；窗口外或无则 None。仅提示，最终判定在创建事务。"""
    now = now or time.time()
    recent = task_store.list_tasks(scope_key=scope_key, creator_id=creator_id, limit=1)
    if not recent:
        return None
    t = recent[0]
    elapsed = now - t["created_at"]
    if elapsed < COOLDOWN_WINDOW:
        return {
            "task_id": t["id"],
            "status": t["status"],
            "remaining": COOLDOWN_WINDOW - elapsed,
        }
    return None


def resolve_workspace(
    scope_key: str, name: str | None
) -> tuple[dict[str, Any] | None, str]:
    """解析创建 Task 使用的 workspace：指定名称验证存在；缺省用 default。

    返回 ``(workspace, "")`` 或 ``(None, 错误提示)``。创建时必须冻结规范化绝对
    root 与读写模式；命令不能传入任意路径。
    """
    if name:
        ws = task_store.get_workspace(scope_key, name)
        if ws is None:
            return None, f"workspace `{name}` 不存在于当前 scope。"
        return ws, ""
    ws = task_store.get_default_workspace(scope_key)
    if ws is None:
        names = [w["name"] for w in task_store.list_workspaces(scope_key)]
        hint = "、".join(names) if names else "（无）"
        return None, f"当前 scope 没有默认 workspace，可用：{hint}"
    return ws, ""
