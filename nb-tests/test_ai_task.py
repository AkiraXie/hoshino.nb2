"""AI Task runtime 单元测试：store CRUD/cooldown、TaskContext round-trip、
scheduler claim/审批/重试、outbox、policy、workspace、matcher 注册。

不连接真实模型：scheduler 成功/失败路径通过 monkeypatch ``run_task_run`` 驱动。
模块级只 import 纯 DTO（``task.models`` 仅依赖 pydantic），避免在 conftest
``load_plugins`` 之前触发 ``providers`` 等插件模块加载。

文件级 ``_nonebot_bootstrap``：``load_plugins`` 会递归把 ``ai/task`` 子包及其
模块注册为插件，若任何 store/scheduler 测试先于 bootstrap 普通 import 它们，
TestMatcher 的 bootstrap 会报 "not loaded as a plugin"。统一先 bootstrap 再跑。
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from _helpers import _create_task, _make_ctx

pytestmark = pytest.mark.usefixtures("_nonebot_bootstrap")


# ------------------------------------------------------------ TaskContext


class TestTaskContextRoundTrip:
    def test_preserves_all_fields_and_frozenset_profile(self):
        from hoshino.ai.task.models import TaskContext

        ctx = _make_ctx(
            conversation_id="conv-x",
            agent_run_id="agent-x",
            persona_prompt="你是研究员",
            permission_json=json.dumps({"user_id": "42", "is_superuser": False, "is_admin": True}),
            tool_profile=frozenset({("bash", 1), ("web_fetch", 1)}),
            extra={"message_history_json": "[]", "pending_deferred": {"c1": True}},
            workdir="/tmp/ws",
            workdir_mode="read_only",
        )
        restored = TaskContext.from_json(ctx.to_json())
        assert restored == ctx
        assert restored.tool_profile == frozenset({("bash", 1), ("web_fetch", 1)})
        assert restored.extra["pending_deferred"] == {"c1": True}
        assert restored.persona_prompt == "你是研究员"

    def test_from_json_missing_fields_use_defaults(self):
        from hoshino.ai.task.models import TaskContext

        restored = TaskContext.from_json({"task_id": "t9"})
        assert restored.task_id == "t9"
        assert restored.scope_key == ""
        assert restored.approval_mode == "auto"
        assert restored.tool_profile == frozenset()


# ------------------------------------------------------------ store CRUD / cooldown


class TestStore:
    def test_create_claim_succeed(self, tmp_store):
        from hoshino.ai.task import store as task_store

        task_id, run_id = _create_task(tmp_store)
        task = task_store.get_task(task_id)
        assert task["status"] == "queued"
        assert task["kind"] == "research"

        run = task_store.claim_next_run("scheduler")
        assert run is not None and run["id"] == run_id
        assert run["state"] == "running"
        assert run["lease_owner"] == "scheduler"

        # 已被 claim，第二次拿不到
        assert task_store.claim_next_run("scheduler") is None

        # heartbeat 续租
        assert task_store.heartbeat(run_id, 99999.0) is True
        run = task_store.get_task_run(run_id)
        assert run["lease_expiry"] == 99999.0

        # 成功落库
        assert task_store.update_run_state(run_id, "succeeded") is True
        task_store.update_task_status(task_id, "succeeded", output_json="{}")
        assert task_store.get_task(task_id)["status"] == "succeeded"

    def test_cooldown_blocks_second_creation(self, tmp_store):
        from hoshino.ai.task import store as task_store

        _create_task(tmp_store, task_id="t1")
        created = task_store.create_task(
            task_id="t2",
            kind="research",
            prompt="x",
            scope_key="milky:123456",
            creator_id="42",
            target_json="{}",
            provider_id="openai",
            model="m",
            context_json="{}",
            snapshot_json="{}",
            event_payloads=[],
            outbox_payloads=[],
        )
        assert created["cooldown"] is True
        assert created["task_id"] == "t1"
        assert 0 < created["remaining"] <= 300.0

    def test_cooldown_bypass_for_superuser(self, tmp_store):
        from hoshino.ai.task import store as task_store

        _create_task(tmp_store, task_id="t1")
        created = task_store.create_task(
            task_id="t2",
            kind="research",
            prompt="x",
            scope_key="milky:123456",
            creator_id="42",
            target_json="{}",
            provider_id="openai",
            model="m",
            context_json="{}",
            snapshot_json="{}",
            event_payloads=[],
            outbox_payloads=[],
            bypass_cooldown=True,
        )
        assert "cooldown" not in created
        assert created["task_id"] == "t2"

    def test_request_cancel_only_before_terminal(self, tmp_store):
        from hoshino.ai.task import store as task_store

        task_id, run_id = _create_task(tmp_store)
        assert task_store.request_cancel(task_id, "42") is True
        task_store.update_run_state(run_id, "cancelled")
        # 终态后不可再取消
        assert task_store.request_cancel(task_id, "42") is False

    def test_count_active_runs(self, tmp_store):
        from hoshino.ai.task import store as task_store

        _create_task(tmp_store, task_id="t1")
        _create_task(tmp_store, task_id="t2", creator_id="7")
        assert task_store.count_active_runs("milky:123456") == 2
        task_store.claim_next_run("scheduler")  # queued -> running，仍活跃
        assert task_store.count_active_runs("milky:123456") == 2

    def test_interrupted_requeue(self, tmp_store):
        from hoshino.ai.task import store as task_store

        task_id, run_id = _create_task(tmp_store)
        task_store.claim_next_run("scheduler")
        # 让 lease 过期 -> 标记 interrupted -> 重新入队（不增加 attempt）
        task_store.heartbeat(run_id, expiry=0.0)
        assert task_store.mark_interrupted_expired(now=1e9) == 1
        assert task_store.get_task_run(run_id)["state"] == "interrupted"
        assert task_store.requeue_interrupted(now=1e9) == 1
        assert task_store.get_task_run(run_id)["state"] == "queued"
        # 可再次 claim，attempt 仍是 1
        run = task_store.claim_next_run("scheduler")
        assert run["attempt"] == 1

    def test_create_next_attempt_advances_and_reuses_context(self, tmp_store):
        from hoshino.ai.task import store as task_store

        task_id, run_id = _create_task(tmp_store)
        task_store.claim_next_run("scheduler")
        ctx = _make_ctx(task_id=task_id, task_run_id=run_id, conversation_id="conv-x")
        task_store.update_run_state(
            run_id, "failed", last_error="boom", context_json=json.dumps(ctx.to_json())
        )
        created = task_store.create_next_attempt(task_id)
        assert created["attempt"] == 2
        assert task_store.get_task(task_id)["status"] == "queued"
        new_run = task_store.get_task_run(created["task_run_id"])
        assert new_run["conversation_id"] == "conv-x"
        assert json.loads(new_run["context_json"])["conversation_id"] == "conv-x"

    def test_heartbeat_rejects_foreign_owner(self, tmp_store):
        """续租只对 claim 时的 owner 生效，防止 lease 被重新 claim 后旧 worker 续租。"""
        from hoshino.ai.task import store as task_store

        task_id, run_id = _create_task(tmp_store)
        claimed = task_store.claim_next_run("scheduler")
        assert claimed is not None and claimed["id"] == run_id
        assert task_store.heartbeat(run_id, 99999.0, owner="scheduler") is True
        assert task_store.heartbeat(run_id, 88888.0, owner="stale-worker") is False
        assert task_store.get_task_run(run_id)["lease_expiry"] == 99999.0

    def test_create_task_freezes_run_identity_and_adapter(self, tmp_store):
        """创建事务一次性冻结 run id / conversation / adapter，上下文不留空窗。"""
        from hoshino.ai.task import store as task_store
        from hoshino.ai.task.models import TaskContext

        ctx = _make_ctx(task_id="t_atomic", task_run_id="r_atomic", conversation_id="conv_atomic")
        created = task_store.create_task(
            task_id="t_atomic",
            kind="research",
            prompt=ctx.prompt,
            scope_key=ctx.scope_key,
            creator_id="42",
            target_json=ctx.target_json,
            provider_id=ctx.provider_id,
            model=ctx.model,
            context_json=json.dumps(ctx.to_json(), ensure_ascii=False),
            snapshot_json="{}",
            event_payloads=[],
            outbox_payloads=[],
            adapter_name="milky",
            task_run_id="r_atomic",
            conversation_id="conv_atomic",
        )
        assert created["task_run_id"] == "r_atomic"
        assert task_store.get_task("t_atomic")["adapter_name"] == "milky"
        run = task_store.get_task_run("r_atomic")
        assert run["conversation_id"] == "conv_atomic"
        restored = TaskContext.from_json(json.loads(run["context_json"]))
        assert restored.task_run_id == "r_atomic"
        assert restored.conversation_id == "conv_atomic"


# ------------------------------------------------------------ policy / workspace


class TestPolicyWorkspace:
    def test_policy_default_and_matrix(self, tmp_store):
        from hoshino.ai.task import policy

        assert policy.get_creation_policy("milky:123456") == "superuser"
        assert policy.policy_allows_creation("superuser", is_superuser=True, is_admin=False)
        assert not policy.policy_allows_creation("superuser", is_superuser=False, is_admin=True)
        assert policy.policy_allows_creation("admin", is_superuser=False, is_admin=True)
        assert policy.policy_allows_creation("all", is_superuser=False, is_admin=False)

        from hoshino.ai.task import store as task_store

        task_store.set_scope_policy("milky:123456", "admin", max_concurrent=1)
        assert policy.get_creation_policy("milky:123456") == "admin"

    def test_concurrent_guard(self, tmp_store):
        from hoshino.ai.task import policy
        from hoshino.ai.task import store as task_store

        task_store.set_scope_policy("milky:123456", "all", max_concurrent=1)
        _create_task(tmp_store)
        allowed, active, cap = policy.check_concurrent("milky:123456")
        assert allowed is False and active == 1 and cap == 1

    def test_workspace_crud_and_default(self, tmp_store):
        from hoshino.ai.task import store as task_store

        assert task_store.add_workspace("milky:123456", "ws", "/tmp/ws", "read_write") == ""
        assert (
            task_store.add_workspace("milky:123456", "ws", "/tmp/other", "read_write") != ""
        )  # 重名拒绝
        assert task_store.set_default_workspace("milky:123456", "ws") is True
        assert task_store.get_default_workspace("milky:123456")["name"] == "ws"
        assert task_store.get_workspace("milky:123456", "ws")["mode"] == "read_write"
        assert task_store.remove_workspace("milky:123456", "ws") is True
        assert task_store.get_workspace("milky:123456", "ws") is None
        # 删掉默认后，另一个 scope 的默认不受影响
        assert task_store.get_default_workspace("milky:other") is None

    def test_resolve_workspace(self, tmp_store):
        from hoshino.ai.task import policy
        from hoshino.ai.task import store as task_store

        ws, err = policy.resolve_workspace("milky:123456", None)
        assert ws is None and "没有默认 workspace" in err
        task_store.add_workspace("milky:123456", "a", "/tmp/a", "read_write")
        task_store.add_workspace("milky:123456", "b", "/tmp/b", "read_write")
        task_store.set_default_workspace("milky:123456", "b")
        ws, err = policy.resolve_workspace("milky:123456", None)
        assert ws["name"] == "b"
        ws, err = policy.resolve_workspace("milky:123456", "a")
        assert ws["name"] == "a"
        ws, err = policy.resolve_workspace("milky:123456", "nope")
        assert ws is None and "不存在" in err


# ------------------------------------------------------------ outbox


class TestOutbox:
    def test_enqueue_sequence_pending_sent(self, tmp_store):
        from hoshino.ai.task import store as task_store

        task_store.outbox_enqueue(
            event_type="task.completed",
            task_id="t1",
            sequence=1,
            target_json="{}",
            payload="{}",
        )
        task_store.outbox_enqueue(
            event_type="task.failed",
            task_id="t1",
            sequence=2,
            target_json="{}",
            payload="{}",
        )
        pending = task_store.outbox_pending(limit=10)
        assert [p["sequence"] for p in pending] == [1, 2]
        task_store.outbox_mark_sent(pending[0]["id"])
        remaining = task_store.outbox_pending(limit=10)
        assert len(remaining) == 1 and remaining[0]["sequence"] == 2

    def test_outbox_retry_increments_attempt(self, tmp_store):
        from hoshino.ai.task import store as task_store

        task_store.outbox_enqueue(
            event_type="task.completed",
            task_id="t1",
            sequence=1,
            target_json="{}",
            payload="{}",
        )
        item = task_store.outbox_pending(limit=1)[0]
        # 重试时间置为过去，模拟下一轮派发窗口到达
        task_store.outbox_mark_retry(item["id"], "send failed", next_retry_at=1.0)
        item = task_store.outbox_pending(limit=1)[0]
        assert item["attempt"] == 1
        assert item["last_error"] == "send failed"

    def test_outbox_gives_up_after_max_attempts(self, tmp_store):
        """超过重试上限后放弃投递：不再进入 pending，不回滚 Task 终态。"""
        from hoshino.ai.task import store as task_store

        task_store.outbox_enqueue(
            event_type="task.completed",
            task_id="t1",
            sequence=1,
            target_json="{}",
            payload="{}",
        )
        item = task_store.outbox_pending(limit=1)[0]
        task_store.outbox_mark_retry(item["id"], "send failed", next_retry_at=1.0, max_attempts=3)
        task_store.outbox_mark_retry(item["id"], "send failed", next_retry_at=1.0, max_attempts=3)
        assert len(task_store.outbox_pending(limit=1)) == 1  # 未达上限仍可重试
        task_store.outbox_mark_retry(item["id"], "send failed", next_retry_at=1.0, max_attempts=3)
        assert task_store.outbox_pending(limit=1) == []  # 达到上限：放弃


# ------------------------------------------------------------ scheduler


class TestScheduler:
    async def test_tick_success_path(self, tmp_store, monkeypatch):
        from hoshino.ai.task import events as task_events
        from hoshino.ai.task import scheduler
        from hoshino.ai.task import store as task_store
        from hoshino.ai.task.models import TaskOutput
        from hoshino.ai.task.runtime import RunOutcome

        task_id, run_id = _create_task(tmp_store)

        class _FakeResult:
            run_id = "agent-run-1"
            conversation_id = "conv-1"

            def usage(self):
                return None

            def all_messages(self):
                return []

        outcome = RunOutcome(
            agent_run_id="agent-run-1",
            conversation_id="conv-1",
            messages_json="[]",
            output=TaskOutput(summary="研究完成", findings=[], sources=[]),
            result=_FakeResult(),
            usage={"total_tokens": 8},
        )

        async def _fake_run(*a, **k):
            return outcome

        monkeypatch.setattr(scheduler, "run_task_run", _fake_run)

        await scheduler._tick()

        assert task_store.get_task(task_id)["status"] == "succeeded"
        assert task_store.get_task_run(run_id)["state"] == "succeeded"
        events = task_store.list_events(task_id)
        assert any(e["event_type"] == task_events.COMPLETED for e in events)
        # outbox 有完成通知
        outbox = task_store.outbox_pending(limit=10)
        assert any(o["event_type"] == task_events.COMPLETED for o in outbox)
        # 终态 Task 不再被 claim
        assert task_store.claim_next_run("scheduler") is None

    async def test_tick_internal_retry(self, tmp_store, monkeypatch):
        from hoshino.ai.task import events as task_events
        from hoshino.ai.task import scheduler
        from hoshino.ai.task import store as task_store
        from hoshino.ai.task.runtime import TaskRuntimeError

        task_id, run_id = _create_task(tmp_store)

        def _boom(*a, **k):
            raise TaskRuntimeError("provider down")

        monkeypatch.setattr(scheduler, "run_task_run", _boom)
        await scheduler._tick()

        run = task_store.get_task_run(run_id)
        assert run["state"] == "retry_wait"
        assert run["retry_count"] == 1
        assert run["next_retry_at"] > 0
        assert task_store.get_task(task_id)["status"] == "queued"
        events = task_store.list_events(task_id)
        assert any(e["event_type"] == task_events.RETRY_SCHEDULED for e in events)

    def test_approval_denied_terminates(self, tmp_store):
        from hoshino.ai.task import scheduler
        from hoshino.ai.task import store as task_store

        task_id, run_id = _create_task(tmp_store)
        task_store.create_approval(
            approval_id="a1",
            task_id=task_id,
            task_run_id=run_id,
            agent_run_id="agent-1",
            tool_call_id="call-1",
            tool_name="bash",
            version=1,
            param_hash="deadbeef",
            param_summary="{cmd=<12>}",
            risk_reason="high_risk_tool",
            creator_id="42",
            expires_at=1e9,
        )
        result = scheduler.resolve_approval("a1", "denied", resolved_by="42")
        assert result["ok"] is True and result["terminal"] == "failed"
        assert task_store.get_task(task_id)["status"] == "failed"
        assert task_store.get_task(task_id)["failure_reason"] == "approval_denied"
        assert task_store.get_task_run(run_id)["state"] == "failed"

    def test_approval_approve_resumes(self, tmp_store):
        from hoshino.ai.task import scheduler
        from hoshino.ai.task import store as task_store

        task_id, run_id = _create_task(tmp_store)
        # 更新 run context（含恢复所需历史），让批准后可回 queued
        ctx = _make_ctx(task_id=task_id, task_run_id=run_id)
        task_store.update_run_state(
            run_id, "waiting_approval", context_json=json.dumps(ctx.to_json())
        )
        task_store.create_approval(
            approval_id="a1",
            task_id=task_id,
            task_run_id=run_id,
            agent_run_id="agent-1",
            tool_call_id="call-1",
            tool_name="bash",
            version=1,
            param_hash="deadbeef",
            param_summary="{cmd=<12>}",
            risk_reason="high_risk_tool",
            creator_id="42",
            expires_at=1e9,
        )
        result = scheduler.resolve_approval("a1", "approved", resolved_by="42")
        assert result["ok"] is True and result["terminal"] == "queued"
        assert task_store.get_task(task_id)["status"] == "queued"
        run = task_store.get_task_run(run_id)
        assert run["state"] == "queued"
        from hoshino.ai.task.models import TaskContext

        ctx_restored = TaskContext.from_json(json.loads(run["context_json"]))
        assert ctx_restored.extra["pending_deferred"] == {"call-1": True}

    def test_approval_creator_only(self, tmp_store):
        from hoshino.ai.task import scheduler
        from hoshino.ai.task import store as task_store

        task_id, run_id = _create_task(tmp_store)
        task_store.create_approval(
            approval_id="a1",
            task_id=task_id,
            task_run_id=run_id,
            agent_run_id="agent-1",
            tool_call_id="call-1",
            tool_name="bash",
            version=1,
            param_hash="h",
            param_summary="{}",
            risk_reason="high_risk_tool",
            creator_id="42",
            expires_at=1e9,
        )
        result = scheduler.resolve_approval("a1", "approved", resolved_by="7")
        assert result["ok"] is False
        assert "创建者" in result["reason"]
        assert task_store.get_task(task_id)["status"] == "queued"

    def test_approval_requires_known_creator(self, tmp_store):
        """创建者或审批人身份缺失时按拒绝处理，不留空串旁路。"""
        from hoshino.ai.task import scheduler
        from hoshino.ai.task import store as task_store

        task_id, run_id = _create_task(tmp_store)
        task_store.create_approval(
            approval_id="a_unknown",
            task_id=task_id,
            task_run_id=run_id,
            agent_run_id="agent-1",
            tool_call_id="call-1",
            tool_name="bash",
            version=1,
            param_hash="h",
            param_summary="{}",
            risk_reason="high_risk_tool",
            creator_id="",
            expires_at=1e9,
        )
        result = scheduler.resolve_approval("a_unknown", "approved", resolved_by="42")
        assert result["ok"] is False
        assert task_store.get_approval("a_unknown")["state"] == "pending"

    def test_pick_bot_matches_task_adapter(self, monkeypatch):
        """outbox 派发挑选与 Task 创建适配器一致的 bot；无匹配返回 None。"""
        import nonebot

        from hoshino.ai.task import scheduler

        milky_bot = SimpleNamespace(adapter=SimpleNamespace(get_name=lambda: "Milky"))
        tg_bot = SimpleNamespace(adapter=SimpleNamespace(get_name=lambda: "Telegram"))
        monkeypatch.setattr(nonebot, "get_bots", lambda: {"m": milky_bot, "t": tg_bot})
        assert scheduler._pick_bot("Milky") is milky_bot
        assert scheduler._pick_bot("Telegram") is tg_bot
        assert scheduler._pick_bot("OneBot V11") is None
        assert scheduler._pick_bot("") is milky_bot  # 无 adapter 记录退回首个在线
        monkeypatch.setattr(nonebot, "get_bots", dict)
        assert scheduler._pick_bot("Milky") is None

    def test_approval_expire(self, tmp_store):
        from hoshino.ai.task import scheduler
        from hoshino.ai.task import store as task_store

        task_id, run_id = _create_task(tmp_store)
        task_store.create_approval(
            approval_id="a1",
            task_id=task_id,
            task_run_id=run_id,
            agent_run_id="agent-1",
            tool_call_id="call-1",
            tool_name="bash",
            version=1,
            param_hash="h",
            param_summary="{}",
            risk_reason="high_risk_tool",
            creator_id="42",
            expires_at=0.0,  # 已过期
        )
        assert scheduler._expire_stale_approvals() == 1
        assert task_store.get_approval("a1")["state"] == "expired"
        assert task_store.get_task(task_id)["status"] == "failed"
        assert task_store.get_task(task_id)["failure_reason"] == "approval_timeout"

    def test_render_notification_redacts_sensitive(self):
        from hoshino.ai.task.scheduler import render_notification

        text = render_notification(
            "task.completed",
            "t1",
            {"kind": "research", "status": "succeeded", "summary": "完成"},
        )
        assert "[AI Task t1]" in text
        assert "完成" in text
        # 不含绝对路径与完整工具参数
        assert "/tmp/ws" not in text
        assert "cmd=" not in text


# ------------------------------------------------------------ matcher 注册


@pytest.mark.usefixtures("_nonebot_bootstrap")
class TestMatcher:
    def test_task_command_registered_with_superuser_permission(self):
        from hoshino.core.permission import SUPERUSER
        from hoshino.modules.ai import task_commands

        def _perm_names(perm):
            names = set()
            for dep in perm.checkers:
                call = dep.call
                names.add(
                    getattr(call, "__qualname__", type(call).__name__)
                    if callable(call)
                    else type(call).__name__
                )
            return names

        assert task_commands.taskcmd.priority == 0
        assert task_commands.taskcmd.block is True
        # 所有 ai 命令统一审批：task 命令挂 SUPERUSER，非超管不可达
        assert _perm_names(task_commands.taskcmd.permission) == _perm_names(SUPERUSER)

    def test_task_matcher_present_in_nonebot_matchers(self):
        from nonebot import get_loaded_plugins

        from hoshino.modules.ai import task_commands

        all_matchers = [m for plugin in get_loaded_plugins() for m in plugin.matcher]
        assert task_commands.taskcmd.matcher in all_matchers
