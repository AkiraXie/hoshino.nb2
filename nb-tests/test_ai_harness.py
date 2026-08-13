"""Harness compatibility facade 单元测试（task-runtime-v1 plan 实施顺序第 8 项）。

harness 作为固定依赖安装（``pydantic-ai-harness``），真实 capability 路径用 pydantic-ai
的 ``FunctionModel`` 驱动多轮工具调用（不连真实模型）；降级路径 monkeypatch
``_HARNESS_AVAILABLE`` 模拟 import 失败。plan/step store 落在 ``tmp_store`` 指向的临时库，
不污染 ``data/db/aichat.db``。本文件不依赖 nonebot，无文件级 bootstrap。
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from pydantic_ai import Agent
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.models.function import FunctionModel

from hoshino.modules.ai import _harness as harness

# ------------------------------------------------------------ helpers


def dump_target_json() -> str:
    """生成合法的 Target JSON（供 TaskContext.target_json，build_task_deps 会 load）。"""
    from hoshino.platform.target import dump_target, group_target

    return dump_target(group_target(123456))


def _model_one_tool_call(tool_name: str = "add_task", args=None):
    """FunctionModel：第一轮调用工具，拿到工具返回后结束。"""

    async def model_function(messages, info):
        tool_returns = [
            p
            for m in messages
            if isinstance(m, ModelRequest)
            for p in m.parts
            if isinstance(p, ToolReturnPart)
        ]
        if not tool_returns:
            return ModelResponse(
                parts=[
                    ToolCallPart(tool_name=tool_name, args=args or {"content": "任务A"})
                ]
            )
        return ModelResponse(parts=[TextPart("完成")])

    return FunctionModel(model_function)


def _run_with_caps(agent: Agent, prompt: str, caps: list):
    async def _go():
        async with agent.iter(prompt, capabilities=caps) as r:
            async for _node in r:
                pass
        return r.result

    return asyncio.run(_go())


# ------------------------------------------------------------ availability / degradation


class TestAvailability:
    def test_harness_installed(self):
        assert harness.harness_available() is True

    def test_builders_return_none_when_unavailable(self, monkeypatch):
        monkeypatch.setattr(harness, "_HARNESS_AVAILABLE", False)
        assert harness.build_planning() is None
        assert harness.build_step_persistence(agent_name="t1") is None
        assert harness.build_skills(".") is None
        assert harness.build_task_capabilities(task_id="t1") == []

    def test_build_task_capabilities_default(self):
        caps = harness.build_task_capabilities(task_id="t_caps")
        assert len(caps) == 2
        assert type(caps[0]).__name__ == "Planning"
        assert type(caps[1]).__name__ == "StepPersistence"

    def test_build_skills_exposed(self, tmp_path):
        skill = harness.build_skills(str(tmp_path))
        assert skill is not None
        assert type(skill).__name__ == "Skills"


# ------------------------------------------------------------ planning injection


class TestPlanningInjection:
    def test_planning_tools_visible_and_callable(self, tmp_store):
        # tmp_store 把 ai_store.engine 指到临时库，_plan_db_path 随之落在 tmp。
        agent = Agent(_model_one_tool_call())
        caps = harness.build_task_capabilities(task_id="t_plan1")
        result = _run_with_caps(agent, "请规划", caps)
        assert result.output == "完成"

    def test_plan_space_isolated_by_task_id(self, tmp_store):
        db = harness._plan_db_path()
        assert db, "engine 应指向临时库"

        store_a = harness.SqlitePlanStore(db, session="task_a")
        store_b = harness.SqlitePlanStore(db, session="task_b")

        async def _seed():
            from pydantic_ai_harness.planning import PlanItem

            await store_a.set_items([PlanItem(id="p1", content="A计划")])
            return len(await store_a.get_items()), len(await store_b.get_items())

        a, b = asyncio.run(_seed())
        assert a == 1
        assert b == 0

    def test_resolver_isolates_by_deps_task_id(self, tmp_store):
        ctx_a = SimpleNamespace(
            deps=SimpleNamespace(task=SimpleNamespace(task_id="t_a"))
        )
        ctx_b = SimpleNamespace(
            deps=SimpleNamespace(task=SimpleNamespace(task_id="t_b"))
        )
        store_a = harness._plan_store_resolver(ctx_a)
        store_b = harness._plan_store_resolver(ctx_b)
        assert type(store_a).__name__ == "SqlitePlanStore"

        async def _seed():
            from pydantic_ai_harness.planning import PlanItem

            await store_a.set_items([PlanItem(id="p1", content="A计划")])
            return len(await store_a.get_items()), len(await store_b.get_items())

        a, b = asyncio.run(_seed())
        assert a == 1
        assert b == 0  # 不同 task_id 的 plan 空间隔离


# ------------------------------------------------------------ step persistence


class TestStepPersistence:
    def test_events_snapshot_and_resume(self, tmp_store):
        # add_task 工具由 Planning 注入；StepPersistence 只记账不注入工具。
        # tmp_store 让 planning 的 plan db 落在临时库，不污染 data/db。
        store = harness.InMemoryStepStore()
        caps = [
            harness.build_planning(enable_subtasks=True),
            harness.build_step_persistence(agent_name="t_step1", store=store),
        ]
        assert caps[0] is not None and caps[1] is not None

        agent = Agent(_model_one_tool_call())
        _run_with_caps(agent, "请执行", caps)

        async def _inspect():
            runs = await store.list_runs()
            sp_run_id = runs[0].run_id
            events = await store.list_events(run_id=sp_run_id)
            snapshot = await store.latest_snapshot(run_id=sp_run_id)
            from pydantic_ai_harness.step_persistence import continue_run

            resumed = await continue_run(store, run_id=sp_run_id)
            return sp_run_id, events, snapshot, resumed

        sp_run_id, events, snapshot, resumed = asyncio.run(_inspect())
        assert sp_run_id.startswith("t_step1-")
        assert events, "应记录 step events"
        assert snapshot is not None, "应保存可续跑 snapshot"
        assert resumed, "continue_run 应恢复 message history"


# ------------------------------------------------------------ task runtime 接线


class TestTaskRuntimeWiring:
    def test_run_task_run_injects_capabilities(self, tmp_store, monkeypatch):
        from hoshino.modules.ai._config import AIConfig, ProviderConfig, ProviderOptions
        from hoshino.modules.ai._task import runtime as task_runtime
        from hoshino.modules.ai._task.models import TaskContext

        captured: dict = {}

        async def fake_run_agent(
            agent,
            prompt,
            *,
            deps=None,
            message_history=None,
            deferred_tool_results=None,
            conversation_id=None,
            output_type=None,
            capabilities=None,
            on_event=None,
        ):
            captured["capabilities"] = capabilities
            return SimpleNamespace(
                run_id="r1",
                conversation_id="c1",
                output=None,
                usage=None,
                all_messages=lambda: [],
            )

        monkeypatch.setattr(
            task_runtime.providers, "build_agent", lambda *a, **k: object()
        )
        monkeypatch.setattr(task_runtime.runner, "run_agent", fake_run_agent)

        config = AIConfig(
            providers={
                "openai": ProviderConfig(
                    config=ProviderOptions(kind="openai_chat", model="gpt-4o-mini")
                )
            }
        )
        ctx = TaskContext(
            task_id="t_wiring",
            task_run_id="r_wiring",
            task_kind="research",
            scope_key="milky:1",
            creator_id="42",
            target_json=dump_target_json(),
            bot_self_id="",
            adapter_name="",
            provider_id="openai",
            model="gpt-4o-mini",
            prompt="x",
        )
        asyncio.run(task_runtime.run_task_run(ctx, config))

        assert captured["capabilities"], "harness 可用时应注入 capabilities"
        assert len(captured["capabilities"]) == 2
