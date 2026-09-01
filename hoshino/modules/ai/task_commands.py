"""AI Task 命令层：创建/状态/列表/审批/取消/workspace 列表。

**全部 ``ai task`` 命令仅超级用户（SUPERUSER）可用**：独立 matcher（``ai task``
前缀，priority 0 先于 ai_admin 的 ``on_command("ai")``），权限在 matcher 层拦截；
handler 内保留创建者/ADMIN 复核作为纵深防御。
"""

from __future__ import annotations

import dataclasses
import json
import uuid

from nonebot.adapters import Bot, Event

from hoshino.ai import deps as ai_deps
from hoshino.ai import persona, provider, skills, tools
from hoshino.ai.base import get_config
from hoshino.ai.task import events as task_events
from hoshino.ai.task import (
    policy,
    scheduler,
)
from hoshino.ai.task import (
    runtime as task_runtime,
)
from hoshino.ai.task import (
    store as task_store,
)
from hoshino.ai.task.models import CapabilitySnapshot, TaskContext, TaskOutput
from hoshino.ai.task.store import new_id
from hoshino.core.permission import SUPERUSER
from hoshino.modules.ai.ai_admin import sv
from hoshino.platform import (
    dump_target,
    event_scope_key,
    get_plaintext,
    get_user_id,
    platform_key,
    send_to_event,
    target_from_event,
)
from hoshino.platform.superuser import is_superuser

_USAGE = (
    "AI Task 命令（仅超级用户）：\n"
    "  ai task research [--workspace <name>] <topic>\n"
    "  ai task plan [--workspace <name>] <goal>\n"
    "  ai task status <task_id>\n"
    "  ai task list\n"
    "  ai task approve <task_id>\n"
    "  ai task deny <task_id>\n"
    "  ai task cancel <task_id>\n"
    "  ai task workspaces"
)

# priority=0 先于 ai_admin 的 on_command("ai")（默认 1）拦截 "ai task ..."；
# 仅 SUPERUSER 可用（所有 ai 命令统一审批）。
taskcmd = sv.on_startswith(
    "ai task", priority=0, only_group=False, block=True, permission=SUPERUSER
)


@taskcmd.handle()
async def _(bot: Bot, event: Event):
    text = get_plaintext(event).strip()
    rest = text.removeprefix("ai task").strip()
    if not rest:
        await send_to_event(bot, event, _USAGE)
        return
    args = rest.split()
    sub, subargs = args[0], args[1:]
    match sub:
        case "research" | "plan":
            await _create(bot, event, sub, subargs)
        case "status":
            await _status(bot, event, subargs)
        case "list":
            await _list(bot, event)
        case "approve":
            await _approve(bot, event, subargs, "approved")
        case "deny":
            await _approve(bot, event, subargs, "denied")
        case "cancel":
            await _cancel(bot, event, subargs)
        case "workspaces":
            await _workspaces(bot, event)
        case _:
            await send_to_event(bot, event, _USAGE)


def _split_flags(args: list[str]) -> tuple[dict[str, str], list[str]]:
    opts: dict[str, str] = {}
    positional: list[str] = []
    index = 0
    while index < len(args):
        arg = args[index]
        if arg.startswith("--"):
            key = arg[2:].replace("-", "_")
            value = args[index + 1] if index + 1 < len(args) else ""
            opts[key] = value
            index += 2
        else:
            positional.append(arg)
            index += 1
    return opts, positional


def _is_superuser(bot: Bot, event: Event) -> bool:
    user_id = get_user_id(event)
    return bool(user_id is not None and is_superuser(bot, user_id))


def _build_prompt(kind: str, topic: str) -> str:
    if kind == "plan":
        return (
            "请针对以下目标制定实施计划。只输出结构化结果（plan），"
            "必要时使用工具调研背景。\n目标：\n" + topic
        )
    return (
        "请研究以下主题并给出结构化结论（research）。必要时使用工具"
        "搜索、抓取并交叉验证来源。\n主题：\n" + topic
    )


def _can_view(task: dict, scope_key: str, permissions) -> bool:
    """status/list/cancel 权限矩阵：创建者 / 本 scope ADMIN / SUPERUSER。"""
    if permissions.is_superuser:
        return True
    if task["creator_id"] and task["creator_id"] == permissions.user_id:
        return True
    return bool(permissions.is_admin and task["scope_key"] == scope_key)


# ------------------------------------------------------------ 创建


async def _create(bot: Bot, event: Event, kind: str, args: list[str]) -> None:
    opts, positional = _split_flags(args)
    topic = " ".join(positional).strip()
    if not topic:
        await send_to_event(bot, event, _USAGE)
        return
    config = get_config()
    scope_key = event_scope_key(bot, event)
    if scope_key is None:
        await send_to_event(bot, event, "无法确定当前 scope。")
        return
    permissions = await ai_deps.build_permission_snapshot(bot, event)

    creation_policy = policy.get_creation_policy(scope_key)
    if not policy.policy_allows_creation(
        creation_policy,
        is_superuser=permissions.is_superuser,
        is_admin=permissions.is_admin,
    ):
        await send_to_event(
            bot,
            event,
            f"当前 scope 的 Task 创建策略为 `{creation_policy}`，你没有创建权限。",
        )
        return

    allowed, active, max_concurrent = policy.check_concurrent(scope_key)
    if not allowed:
        await send_to_event(
            bot,
            event,
            f"当前 scope 并发 Task 已达上限（{active}/{max_concurrent}）。",
        )
        return

    workspace, ws_error = policy.resolve_workspace(scope_key, opts.get("workspace"))
    if ws_error:
        await send_to_event(bot, event, ws_error)
        return

    provider_id, model = provider.resolve_model(scope_key)
    if not provider_id or not model:
        await send_to_event(bot, event, "未配置模型，请超级用户 `ai model default`。")
        return
    if not provider.has_provider(provider_id):
        await send_to_event(bot, event, "AI 配置异常：provider 不存在。")
        return

    approval_mode = (
        config.task_approval_mode
        if config.task_approval_mode in ("auto", "always", "never")
        else "auto"
    )
    prompt = _build_prompt(kind, topic)
    persona_prompt = persona.resolve_prompt(scope_key, config)
    skill_names = [s.name for s in skills.list_enabled(scope_key)]
    tool_profile = tools.freeze_tool_profile(scope_key)

    task_id = new_id("t")
    task_run_id = new_id("r")
    conversation_id = uuid.uuid4().hex
    adapter_name = platform_key(bot)
    target = target_from_event(bot, event)
    target_json = dump_target(target)

    snapshot = CapabilitySnapshot(
        persona_id=ai_store_get_scope_persona(scope_key),
        persona_version=0,
        skill_names=skill_names,
        enabled_categories=tools.enabled_task_categories(scope_key),
        tool_profile=tool_profile,
        workspace_id=workspace["id"],
        workspace_root=workspace["root"],
        workspace_mode=workspace["mode"],
        approval_mode=approval_mode,
    )
    ctx = TaskContext(
        task_id=task_id,
        task_run_id=task_run_id,
        task_kind=kind,
        scope_key=scope_key,
        creator_id=permissions.user_id or "",
        target_json=target_json,
        bot_self_id=bot.self_id,
        adapter_name=adapter_name,
        provider_id=provider_id,
        model=model,
        prompt=prompt,
        conversation_id=conversation_id,
        workdir=workspace["root"],
        workdir_mode=workspace["mode"],
        approval_mode=approval_mode,
        persona_prompt=persona_prompt,
        permission_json=task_runtime.permission_to_json(permissions),
        tool_profile=frozenset(tool_profile.items()),
    )

    created = task_store.create_task(
        task_id=task_id,
        kind=kind,
        prompt=prompt,
        scope_key=scope_key,
        creator_id=permissions.user_id or "",
        target_json=target_json,
        provider_id=provider_id,
        model=model,
        context_json=ctx.to_json(),
        snapshot_json=json.dumps(dataclasses.asdict(snapshot), ensure_ascii=False),
        event_payloads=[
            {
                "event_type": task_events.CREATED,
                "payload": json.dumps({"kind": kind}, ensure_ascii=False),
            },
            {"event_type": task_events.QUEUED, "payload": "{}"},
        ],
        outbox_payloads=[
            {
                "event_type": task_events.CREATED,
                "sequence": 1,
                "payload": json.dumps({"kind": kind, "status": "accepted"}, ensure_ascii=False),
            }
        ],
        adapter_name=adapter_name,
        bypass_cooldown=bool(permissions.is_superuser),
        task_run_id=task_run_id,
        conversation_id=conversation_id,
    )
    if created.get("cooldown"):
        await send_to_event(
            bot,
            event,
            f"5 分钟内已创建过 Task（{created['task_id']}，状态 "
            f"{created['status']}），剩余 {int(created['remaining'])} 秒后重试。",
        )
        return

    task_events.enqueue_notification(
        task_events.QUEUED,
        task_id=task_id,
        target_json=target_json,
        payload={"kind": kind, "status": "queued"},
    )
    await send_to_event(
        bot,
        event,
        f"Task 已接受：`{task_id}`（{kind}）\n"
        f"将在后台执行，可用 `ai task status {task_id}` 查看进度。",
    )


def ai_store_get_scope_persona(scope_key: str) -> int | None:
    """scope 级 persona id（capability snapshot 冻结用）。"""
    from hoshino.ai import store as ai_store

    return ai_store.get_scope_persona_id(scope_key)


# ------------------------------------------------------------ 状态 / 列表


async def _status(bot: Bot, event: Event, args: list[str]) -> None:
    if not args:
        await send_to_event(bot, event, _USAGE)
        return
    task_id = args[0]
    task = task_store.get_task(task_id)
    if task is None:
        await send_to_event(bot, event, f"Task `{task_id}` 不存在。")
        return
    scope_key = event_scope_key(bot, event) or ""
    permissions = await ai_deps.build_permission_snapshot(bot, event)
    if not _can_view(task, scope_key, permissions):
        await send_to_event(bot, event, "无权限查看该 Task。")
        return

    lines = [f"Task `{task_id}`（{task['kind']}）", f"状态：{task['status']}"]
    if task["failure_reason"]:
        lines.append(f"失败原因：{task['failure_reason']}")
    run = task_store.get_task_run_for_task(task_id)
    if run is not None:
        lines.append(f"attempt：{run['attempt']}，运行状态：{run['state']}")
    pending = [a for a in task_store.list_approvals(task_id) if a["state"] == "pending"]
    if pending:
        lines.append(f"待审批：{len(pending)} 个（`ai task approve/deny {task_id}`）")
    if task["output_json"]:
        try:
            output = TaskOutput.model_validate_json(task["output_json"])
        except Exception:
            output = None
        if output is not None and output.summary:
            lines.append(f"摘要：{output.summary}")
    await send_to_event(bot, event, "\n".join(lines))


async def _list(bot: Bot, event: Event) -> None:
    """权限矩阵：创建者看自己的；ADMIN/OWNER 看本 scope；SUPERUSER 看任意。"""
    scope_key = event_scope_key(bot, event)
    permissions = await ai_deps.build_permission_snapshot(bot, event)
    if permissions.is_superuser:
        tasks = task_store.list_tasks(limit=10)
    elif permissions.is_admin:
        tasks = task_store.list_tasks(scope_key=scope_key, limit=10)
    else:
        tasks = task_store.list_tasks(
            scope_key=scope_key, creator_id=permissions.user_id or "", limit=10
        )
    if not tasks:
        await send_to_event(bot, event, "当前 scope 还没有 Task。")
        return
    lines = [f"近期 Task（{scope_key or '全部'}）："]
    lines.extend(f"- `{t['id']}` {t['kind']} {t['status']}" for t in tasks)
    await send_to_event(bot, event, "\n".join(lines))


# ------------------------------------------------------------ 审批 / 取消


async def _approve(bot: Bot, event: Event, args: list[str], state: str) -> None:
    if not args:
        await send_to_event(bot, event, _USAGE)
        return
    task_id = args[0]
    pending = [a for a in task_store.list_approvals(task_id) if a["state"] == "pending"]
    if not pending:
        await send_to_event(bot, event, "该 Task 没有待审批项。")
        return
    user_id = get_user_id(event)
    uid = str(user_id) if user_id is not None else ""
    result = None
    for approval in pending:
        result = scheduler.resolve_approval(approval["id"], state, uid)
        if not result["ok"]:
            await send_to_event(bot, event, result["reason"])
            return
    if result is None:
        return
    terminal = result.get("terminal")
    if state == "approved":
        if terminal == "queued":
            message = "已批准全部待审批项，Task 恢复执行。"
        elif terminal == "failed":
            message = "存在已拒绝的审批，Task 已失败。"
        else:
            message = "已批准该审批项（仍有其他待审批项）。"
    else:
        if terminal == "failed":
            message = "已拒绝，Task 已失败。"
        else:
            message = "已拒绝该审批项（仍有其他待审批项）。"
    await send_to_event(bot, event, message)


async def _cancel(bot: Bot, event: Event, args: list[str]) -> None:
    if not args:
        await send_to_event(bot, event, _USAGE)
        return
    task_id = args[0]
    task = task_store.get_task(task_id)
    if task is None:
        await send_to_event(bot, event, f"Task `{task_id}` 不存在。")
        return
    scope_key = event_scope_key(bot, event) or ""
    permissions = await ai_deps.build_permission_snapshot(bot, event)
    if not _can_view(task, scope_key, permissions):
        await send_to_event(bot, event, "无权限取消该 Task。")
        return
    if not task_store.request_cancel(task_id, permissions.user_id or ""):
        await send_to_event(bot, event, "Task 已到终态，无法取消。")
        return
    task_events.emit(
        task_events.CANCELLED,
        scope_key=task["scope_key"],
        task_id=task_id,
        task_run_id=(task_store.get_task_run_for_task(task_id) or {}).get("id", ""),
        payload={"reason": "user_cancelled"},
    )
    task_events.enqueue_notification(
        task_events.CANCELLED,
        task_id=task_id,
        target_json=task["target_json"],
        payload={
            "kind": task["kind"],
            "status": "cancelled",
            "reason": "user_cancelled",
        },
    )
    await send_to_event(bot, event, "已请求取消该 Task。")


# ------------------------------------------------------------ workspace


async def _workspaces(bot: Bot, event: Event) -> None:
    scope_key = event_scope_key(bot, event)
    workspaces = task_store.list_workspaces(scope_key)
    if not workspaces:
        await send_to_event(bot, event, "当前 scope 未绑定 workspace。")
        return
    # 本机绝对路径只对 ADMIN+ 展示，普通成员只看名称/模式（不泄露本机路径）。
    permissions = await ai_deps.build_permission_snapshot(bot, event)
    show_root = permissions.is_admin or permissions.is_superuser
    lines = ["已绑定 workspace："]
    for ws in workspaces:
        mark = "（默认）" if ws["is_default"] else ""
        root = f" {ws['root']}" if show_root else ""
        lines.append(f"- {ws['name']}{root} [{ws['mode']}]{mark}")
    await send_to_event(bot, event, "\n".join(lines))
