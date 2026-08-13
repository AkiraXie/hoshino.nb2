"""稳定领域事件 facade。

事件类型名固定（plan 12），schema version 稳定；payload 只含脱敏字段，不落原始
prompt、完整工具参数或内部 thinking。内部遥测事件与稳定事件共用同一张
``ai_task_events`` 表，用 ``event_type`` 前缀区分。outbox 幂等键为
``(task_id, event_type, sequence)``。
"""

from __future__ import annotations

import json
from typing import Any

from . import store

CREATED = "task.created"
QUEUED = "task.queued"
STARTED = "task.started"
RUN_RESTARTED = "task.run_restarted"
PHASE_STARTED = "task.phase_started"
PHASE_COMPLETED = "task.phase_completed"
APPROVAL_REQUESTED = "task.approval_requested"
APPROVAL_RESOLVED = "task.approval_resolved"
RETRY_SCHEDULED = "task.retry_scheduled"
COMPLETED = "task.completed"
FAILED = "task.failed"
CANCELLED = "task.cancelled"

SCHEMA_VERSION = 1


def emit(
    event_type: str,
    *,
    scope_key: str,
    task_id: str,
    task_run_id: str = "",
    agent_run_id: str = "",
    payload: dict[str, Any] | None = None,
) -> int:
    """追加一条稳定领域事件，返回 sequence。"""
    return store.append_event(
        event_type,
        task_id=task_id,
        task_run_id=task_run_id,
        agent_run_id=agent_run_id,
        scope_key=scope_key,
        payload=json.dumps(payload or {}, ensure_ascii=False),
    )


def enqueue_notification(
    event_type: str,
    *,
    task_id: str,
    target_json: str,
    payload: dict[str, Any] | None = None,
) -> None:
    """把用户侧通知写入 outbox（发送失败不阻塞 Task 终态，见 plan 6.2/12）。

    sequence 自动取该 task 下一个序号，保证 (task_id, event_type, sequence) 幂等。
    """
    store.outbox_enqueue(
        event_type=event_type,
        task_id=task_id,
        sequence=store.outbox_next_sequence(task_id),
        target_json=target_json,
        payload=json.dumps(payload or {}, ensure_ascii=False),
    )
