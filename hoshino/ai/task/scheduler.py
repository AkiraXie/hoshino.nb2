"""后台 Task 队列：claim/lease/heartbeat、有限重试、持久化取消、启动恢复、审批。

``on_post_startup`` 启动两个循环：执行队列（claim → runtime → 落库）与 outbox 派发。
测试环境不触发 ``driver.run()`` 所以不会自动启动；测试直接调用 ``_tick`` /
``resolve_approval`` / ``_expire_stale_approvals``。
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
import traceback
import uuid

from loguru import logger
from nonebot import get_bots
from pydantic_ai.tools import DeferredToolResults

from hoshino.core.hooks import on_post_startup, on_shutdown
from hoshino.platform.message import send_to_target
from hoshino.platform.target import load_target, platform_key

from .. import errors, metrics
from ..base import get_config
from . import events as task_events
from . import store as task_store
from .models import TaskContext, TaskOutput
from .runtime import TaskRuntimeError, run_task_run

_LEASE_SECONDS = 120.0
_HEARTBEAT_INTERVAL = 30.0
_APPROVAL_WINDOW = 600.0
_MAX_INTERNAL_RETRIES = 2
_MAX_ATTEMPTS = 3
_TICK_INTERVAL = 1.0
_OUTBOX_INTERVAL = 1.0

_running: set[asyncio.Task] = set()
_stop = asyncio.Event()


def _now() -> float:
    return time.time()


# ------------------------------------------------------------ 工具


def _params_summary(args) -> str:
    """脱敏参数摘要：只列键名与值长度，不落完整参数。"""
    if args is None:
        return "{}"
    if isinstance(args, str):
        return f"<str:{len(args)}>"
    if isinstance(args, dict):
        parts = []
        for key, value in args.items():
            if isinstance(value, str | bytes):
                parts.append(f"{key}=<{len(value)}>")
            else:
                parts.append(f"{key}={type(value).__name__}")
        return "{" + ", ".join(parts) + "}"
    return type(args).__name__


def _params_hash(args) -> str:
    payload = json.dumps(args, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def _deferred_from_ctx(ctx: TaskContext):
    """从 ctx.extra 恢复审批决议；无 pending 返回 None。"""
    pending = ctx.extra.get("pending_deferred")
    if not pending:
        return None
    return DeferredToolResults(approvals=dict(pending))


# ------------------------------------------------------------ 通知渲染


def render_notification(event_type: str, task_id: str, payload: dict) -> str:
    """用户侧通知文本：只含状态/摘要/原因，不泄露绝对路径与完整工具参数。"""
    kind = payload.get("kind", "")
    lines = [f"[AI Task {task_id}]"]
    if kind:
        lines.append(f"任务：{kind}")
    status = payload.get("status")
    if status:
        lines.append(f"状态：{status}")
    if payload.get("reason"):
        lines.append(f"原因：{payload['reason']}")
    if payload.get("summary"):
        lines.append(f"摘要：{payload['summary']}")
    if payload.get("pending_approvals"):
        lines.append(f"待审批工具：{payload['pending_approvals']} 个")
    return "\n".join(lines)


# ------------------------------------------------------------ 主循环


async def _scheduler_loop() -> None:
    while not _stop.is_set():
        try:
            await _tick()
        except Exception as exc:
            logger.warning(
                f"task scheduler tick error={type(exc).__name__} "
                f"detail={errors.format_exception_detail(exc)}"
            )
        await asyncio.sleep(_TICK_INTERVAL)
    logger.info("task scheduler stopped")


async def _tick() -> None:
    """claim 一个到期 TaskRun 并执行；无到期则返回。测试可直接调用。"""
    run = task_store.claim_next_run("scheduler")
    if run is None:
        return
    task = task_store.get_task(run["task_id"])
    if task is None:
        task_store.update_run_state(run["id"], "failed", last_error="task missing")
        return
    if task["status"] == "cancelled":
        task_store.update_run_state(run["id"], "cancelled")
        return
    try:
        ctx = TaskContext.from_json(json.loads(run["context_json"]))
    except (ValueError, TypeError) as exc:
        task_store.update_run_state(run["id"], "failed", last_error="bad context")
        task_store.update_task_status(run["task_id"], "failed", failure_reason="bad_context")
        logger.warning(
            f"task {task['id']} context 解析失败 error={type(exc).__name__} "
            f"detail={errors.format_exception_detail(exc)}"
        )
        return
    await _execute_claimed(run, task, ctx)


async def _execute_claimed(run: dict, task: dict, ctx: TaskContext) -> None:
    """执行一个已 claim 的 TaskRun：Agent run → 终态/审批/重试。"""
    config = get_config()
    task_store.update_task_status(task["id"], "running")
    task_events.emit(
        task_events.STARTED,
        scope_key=task["scope_key"],
        task_id=task["id"],
        task_run_id=run["id"],
        payload={"attempt": run["attempt"]},
    )

    cancelled = False
    last_hb = _now()

    def on_event(ev) -> None:
        nonlocal cancelled, last_hb
        now = _now()
        if now - last_hb >= _HEARTBEAT_INTERVAL:
            task_store.heartbeat(run["id"], now + _LEASE_SECONDS, now=now, owner=run["lease_owner"])
            last_hb = now
        cur = task_store.get_task(task["id"])
        if cur is not None and cur["status"] == "cancelled":
            cancelled = True

    deferred = _deferred_from_ctx(ctx)
    try:
        outcome = await run_task_run(ctx, config, deferred=deferred, on_event=on_event)
    except Exception as exc:
        await _handle_failure(run, task, ctx, exc)
        return

    if cancelled:
        task_store.update_run_state(run["id"], "cancelled")
        task_store.update_task_status(task["id"], "cancelled")
        task_events.emit(
            task_events.CANCELLED,
            scope_key=task["scope_key"],
            task_id=task["id"],
            task_run_id=run["id"],
            agent_run_id=outcome.agent_run_id,
        )
        _notify(task_events.CANCELLED, task, {"status": "cancelled"})
        return

    # 更新恢复上下文：最新 agent run / conversation / message history
    ctx.agent_run_id = outcome.agent_run_id
    ctx.conversation_id = outcome.conversation_id
    ctx.extra["message_history_json"] = outcome.messages_json

    if outcome.deferred:
        await _handle_approval_request(run, task, ctx, outcome)
        return

    if not isinstance(outcome.output, TaskOutput):
        await _handle_failure(run, task, ctx, TaskRuntimeError("invalid structured output"))
        return

    # 成功：结果落库与 Task 完成在同一逻辑步骤内
    task_store.update_run_state(
        run["id"],
        "succeeded",
        agent_run_id=outcome.agent_run_id,
        context_json=json.dumps(ctx.to_json(), ensure_ascii=False),
    )
    task_store.update_task_status(
        task["id"], "succeeded", output_json=outcome.output.model_dump_json()
    )
    metrics.record_success(
        provider_id=ctx.provider_id,
        scope_key=ctx.scope_key,
        model=ctx.model,
        snapshot=metrics.snapshot_from_result(outcome.result),
        latency_ms=0.0,
    )
    task_events.emit(
        task_events.COMPLETED,
        scope_key=task["scope_key"],
        task_id=task["id"],
        task_run_id=run["id"],
        agent_run_id=outcome.agent_run_id,
        payload={"summary": outcome.output.summary},
    )
    _notify(
        task_events.COMPLETED,
        task,
        {
            "status": "succeeded",
            "summary": outcome.output.summary,
        },
    )
    logger.info(
        f"task completed id={task['id']} run={run['id']} tokens={outcome.usage.get('total_tokens')}"
    )


async def _handle_approval_request(run: dict, task: dict, ctx: TaskContext, outcome) -> None:
    """DeferredToolRequests → 为每个 high-risk tool call 创建独立 approval。"""
    requests = outcome.output
    now = _now()
    for call in getattr(requests, "approvals", []) or []:
        args = getattr(call, "args", None)
        task_store.create_approval(
            approval_id=f"a_{uuid.uuid4().hex[:16]}",
            task_id=task["id"],
            task_run_id=run["id"],
            agent_run_id=outcome.agent_run_id,
            tool_call_id=call.tool_call_id,
            tool_name=call.tool_name,
            version=1,
            param_hash=_params_hash(args),
            param_summary=_params_summary(args),
            risk_reason="high_risk_tool",
            creator_id=task["creator_id"],
            expires_at=now + _APPROVAL_WINDOW,
        )
    task_store.update_run_state(
        run["id"],
        "waiting_approval",
        agent_run_id=outcome.agent_run_id,
        context_json=json.dumps(ctx.to_json(), ensure_ascii=False),
    )
    task_store.update_task_status(task["id"], "waiting_approval")
    task_events.emit(
        task_events.APPROVAL_REQUESTED,
        scope_key=task["scope_key"],
        task_id=task["id"],
        task_run_id=run["id"],
        agent_run_id=outcome.agent_run_id,
        payload={"pending_approvals": len(requests.approvals or [])},
    )
    _notify(
        task_events.APPROVAL_REQUESTED,
        task,
        {
            "status": "waiting_approval",
            "pending_approvals": len(requests.approvals or []),
        },
    )


async def _handle_failure(run: dict, task: dict, ctx: TaskContext, exc: Exception) -> None:
    """内部有限重试 → 新 attempt → 终态 failed。"""
    # 完整错误详情（message + body/status/tool）写入 last_error 与日志；
    # 用户可见的 failure_reason / 通知仍保持短类型名。
    detail = errors.format_exception_detail(exc)
    current = task_store.get_task_run(run["id"]) or run
    retries = current.get("retry_count", 0)
    if retries < _MAX_INTERNAL_RETRIES:
        backoff = float(2 ** (retries + 1))
        task_store.update_run_state(
            run["id"],
            "retry_wait",
            retry_count=retries + 1,
            next_retry_at=_now() + backoff,
            last_error=detail,
            context_json=json.dumps(ctx.to_json(), ensure_ascii=False),
        )
        task_store.update_task_status(task["id"], "queued")
        task_events.emit(
            task_events.RETRY_SCHEDULED,
            scope_key=task["scope_key"],
            task_id=task["id"],
            task_run_id=run["id"],
            payload={
                "attempt": run["attempt"],
                "retry": retries + 1,
                "error": type(exc).__name__,
            },
        )
        logger.info(
            f"task retry scheduled id={task['id']} retry={retries + 1} "
            f"error={type(exc).__name__} detail={detail}"
        )
        return

    if current.get("attempt", 1) < _MAX_ATTEMPTS:
        created = task_store.create_next_attempt(task["id"])
        task_events.emit(
            task_events.RUN_RESTARTED,
            scope_key=task["scope_key"],
            task_id=task["id"],
            task_run_id=run["id"],
            payload={
                "from_attempt": run["attempt"],
                "to_attempt": created["attempt"] if created else None,
            },
        )
        logger.warning(
            f"task attempt advanced id={task['id']} "
            f"from={run['attempt']} error={type(exc).__name__} detail={detail}"
        )
        return

    task_store.update_run_state(run["id"], "failed", last_error=detail)
    task_store.update_task_status(
        task["id"], "failed", failure_reason=f"run_error:{type(exc).__name__}"
    )
    task_events.emit(
        task_events.FAILED,
        scope_key=task["scope_key"],
        task_id=task["id"],
        task_run_id=run["id"],
        payload={"reason": type(exc).__name__},
    )
    _notify(
        task_events.FAILED,
        task,
        {"status": "failed", "reason": f"run_error:{type(exc).__name__}"},
    )
    logger.warning(
        f"task failed id={task['id']} run={run['id']} error={type(exc).__name__} detail={detail}"
    )
    logger.debug(f"task failed traceback id={task['id']} run={run['id']}\n{traceback.format_exc()}")


def _notify(event_type: str, task: dict, payload: dict) -> None:
    """把用户侧通知写入 outbox（target 来自 task 序列化 Target）。"""
    try:
        task_events.enqueue_notification(
            event_type,
            task_id=task["id"],
            target_json=task["target_json"],
            payload=payload,
        )
    except Exception as exc:
        logger.warning(
            f"task notification enqueue failed id={task['id']} error={type(exc).__name__}"
        )


# ------------------------------------------------------------ 审批


def resolve_approval(approval_id: str, state: str, resolved_by: str) -> dict:
    """approve/deny 决议；只有 Task 创建者可审批。

    返回给命令层的 dict：``{"ok", "reason", "task_id", ...}``。全部审批决议后：
    任一 deny → Task/TaskRun failed（approval_denied）；全 approve → 回 queued 并
    保存恢复上下文（message history + DeferredToolResults）。
    """
    appr = task_store.get_approval(approval_id)
    if appr is None:
        return {"ok": False, "reason": "审批不存在。", "task_id": ""}
    if appr["state"] != "pending":
        return {
            "ok": False,
            "reason": f"该审批已 {appr['state']}。",
            "task_id": appr["task_id"],
        }
    # 创建者缺失或审批人身份缺失时按拒绝处理（安全默认），不留空串旁路。
    if not resolved_by or resolved_by != appr["creator_id"]:
        return {
            "ok": False,
            "reason": "只有 Task 创建者可以审批。",
            "task_id": appr["task_id"],
        }
    if not task_store.resolve_approval(approval_id, state, resolved_by):
        return {
            "ok": False,
            "reason": "审批状态已变化，请重新查看。",
            "task_id": appr["task_id"],
        }
    return _after_approval(appr["task_id"], appr["task_run_id"], state)


def _after_approval(task_id: str, task_run_id: str, state: str) -> dict:
    approvals = task_store.list_approvals(task_id)
    if any(a["state"] == "pending" for a in approvals):
        return {"ok": True, "task_id": task_id, "pending": True}
    if any(a["state"] == "denied" for a in approvals):
        task_store.update_run_state(task_run_id, "failed", last_error="approval_denied")
        task_store.update_task_status(task_id, "failed", failure_reason="approval_denied")
        task = task_store.get_task(task_id) or {}
        task_events.emit(
            task_events.FAILED,
            scope_key=(task.get("scope_key") or ""),
            task_id=task_id,
            task_run_id=task_run_id,
            payload={"reason": "approval_denied"},
        )
        _notify(
            task_events.FAILED,
            task,
            {"status": "failed", "reason": "approval_denied"},
        )
        return {"ok": True, "task_id": task_id, "pending": False, "terminal": "failed"}

    # 全部 approved → 恢复执行：保存 DeferredToolResults 与历史，回 queued
    run = task_store.get_task_run(task_run_id)
    ctx = None
    if run is not None:
        try:
            ctx = TaskContext.from_json(json.loads(run["context_json"]))
        except (ValueError, TypeError) as exc:
            # 恢复上下文损坏 → run 无法继续执行：置 failed 收尾，避免 run 永久
            # 停在 waiting_approval 而 task 已回 queued（调度器只 claim
            # queued/retry_wait，二者不一致会导致任务卡死）。
            ctx = None
            task_store.update_run_state(
                task_run_id,
                "failed",
                last_error=f"bad approval context: {type(exc).__name__}",
            )
            task_store.update_task_status(task_id, "failed", failure_reason="bad_context")
            task = task_store.get_task(task_id) or {}
            task_events.emit(
                task_events.FAILED,
                scope_key=(task.get("scope_key") or ""),
                task_id=task_id,
                task_run_id=task_run_id,
                payload={"reason": "bad_context"},
            )
            _notify(
                task_events.FAILED,
                task,
                {"status": "failed", "reason": "bad_context"},
            )
            logger.warning(
                f"task approval context 解析失败，置 failed id={task_id} "
                f"run={task_run_id} error={type(exc).__name__}"
            )
            return {
                "ok": True,
                "task_id": task_id,
                "pending": False,
                "terminal": "failed",
            }
    if ctx is not None:
        ctx.extra["pending_deferred"] = {a["tool_call_id"]: True for a in approvals}
        task_store.update_run_state(
            task_run_id,
            "queued",
            context_json=json.dumps(ctx.to_json(), ensure_ascii=False),
            next_retry_at=_now(),
        )
    task_store.update_task_status(task_id, "queued")
    task = task_store.get_task(task_id) or {}
    task_events.emit(
        task_events.APPROVAL_RESOLVED,
        scope_key=(task.get("scope_key") or ""),
        task_id=task_id,
        task_run_id=task_run_id,
    )
    _notify(
        task_events.APPROVAL_RESOLVED,
        task,
        {"status": "queued"},
    )
    return {"ok": True, "task_id": task_id, "pending": False, "terminal": "queued"}


def _expire_stale_approvals() -> int:
    """超时 approval → expired，Task/TaskRun failed（approval_timeout）。"""
    expired = task_store.expire_approvals(now=_now())
    for appr in expired:
        task_store.update_run_state(appr["task_run_id"], "failed", last_error="approval_timeout")
        task_store.update_task_status(appr["task_id"], "failed", failure_reason="approval_timeout")
        task = task_store.get_task(appr["task_id"]) or {}
        task_events.emit(
            task_events.FAILED,
            scope_key=(task.get("scope_key") or ""),
            task_id=appr["task_id"],
            task_run_id=appr["task_run_id"],
            payload={"reason": "approval_timeout"},
        )
        _notify(
            task_events.FAILED,
            task,
            {"status": "failed", "reason": "approval_timeout"},
        )
    return len(expired)


# ------------------------------------------------------------ outbox 派发


async def _outbox_loop() -> None:
    while not _stop.is_set():
        try:
            items = task_store.outbox_pending(limit=10)
        except Exception as exc:
            logger.warning(f"task outbox scan error={type(exc).__name__}")
            await asyncio.sleep(5.0)
            continue
        for item in items:
            try:
                ok = await _deliver(item)
            except Exception:
                ok = False
            if ok:
                task_store.outbox_mark_sent(item["id"])
            else:
                task_store.outbox_mark_retry(item["id"], "send failed")
        if not items:
            await asyncio.sleep(_OUTBOX_INTERVAL)


def _pick_bot(adapter_name: str):
    """挑选与 Task 创建适配器一致的 bot；无匹配时返回 None（由 outbox 重试）。

    不能随手取第一个在线 bot：跨适配器的 Target 无法经由它发送，会永久失败。
    """
    bots = get_bots()
    if not bots:
        return None
    if adapter_name:
        key = platform_key(adapter_name=adapter_name)
        for bot in bots.values():
            if platform_key(bot) == key:
                return bot
        return None
    return next(iter(bots.values()))


async def _deliver(item: dict) -> bool:
    """向持久化 Target 发送一条 outbox 通知；失败返回 False（由 outbox 重试）。"""
    try:
        target = load_target(item["target_json"])
        task = task_store.get_task(item["task_id"])
        bot = _pick_bot((task or {}).get("adapter_name", ""))
        if bot is None:
            return False
        payload = json.loads(item["payload_json"])
        text = render_notification(item["event_type"], item["task_id"], payload)
        await send_to_target(bot, target, text)
        return True
    except Exception as exc:
        logger.warning(f"task outbox deliver failed id={item['id']} error={type(exc).__name__}")
        return False


# ------------------------------------------------------------ 生命周期


@on_post_startup
async def _start_scheduler() -> None:
    """启动恢复：过期 running → interrupted → 可安全重跑者重新入队；启动循环。"""
    now = _now()
    task_store.mark_interrupted_expired(now=now)
    task_store.requeue_interrupted(now=now)
    _expire_stale_approvals()
    _running.add(asyncio.create_task(_scheduler_loop()))
    _running.add(asyncio.create_task(_outbox_loop()))
    logger.info("task scheduler started")


@on_shutdown
async def _stop_scheduler() -> None:
    _stop.set()
    for task in list(_running):
        task.cancel()
