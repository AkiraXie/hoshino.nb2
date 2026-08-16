"""跨测试文件共享的 helper：Milky 事件构造与 AI Task 工厂。

这些 helper 原先散落在 test_milky_adapter.py / test_ai_task.py，被多个测试文件
跨文件 import；下沉到本模块使 import 关系清晰。函数均为纯构造，不依赖各测试
文件的模块级状态；业务模块一律函数内 import（沿用各来源文件的导入纪律）。

本文件不匹配 pytest 的测试收集规则（非 test_* 前缀），不会被当作测试模块。
"""

from __future__ import annotations

import json

from nonebot import get_adapters
from nonebot.adapters.milky import Adapter as MilkyAdapter
from nonebot.adapters.milky import Bot as MilkyBot
from nonebot.adapters.milky.config import ClientInfo
from nonebot.adapters.milky.event import GroupMessageEvent as MilkyGroupMessageEvent

from conftest import next_seq


def _milky_group_message(
    text: str,
    *,
    to_me: bool,
    user_id: int = 42,
) -> tuple[MilkyBot, MilkyGroupMessageEvent]:
    adapter = get_adapters()[MilkyAdapter.get_name()]
    bot = MilkyBot(adapter, self_id="10000", info=ClientInfo())
    event = adapter.json_to_event(
        {
            "event_type": "message_receive",
            "time": 1,
            "self_id": 10000,
            "data": {
                "message_scene": "group",
                "peer_id": 123456,
                "message_seq": next_seq(),
                "sender_id": user_id,
                "time": 1,
                "segments": [{"type": "text", "data": {"text": text}}],
                "group": {
                    "group_id": 123456,
                    "group_name": "test group",
                    "member_count": 2,
                    "max_member_count": 100,
                },
                "group_member": {
                    "user_id": user_id,
                    "nickname": "Alice",
                    "sex": "unknown",
                    "group_id": 123456,
                    "card": "Alice member",
                    "title": "",
                    "level": 1,
                    "role": "admin",
                    "join_time": 1,
                    "last_sent_time": 1,
                },
            },
        }
    )
    assert isinstance(event, MilkyGroupMessageEvent)
    event.to_me = to_me
    return bot, event


_ctx_defaults = {
    "task_kind": "research",
    "scope_key": "milky:123456",
    "creator_id": "42",
    "target_json": json.dumps({"scene": "group", "peer": "123456"}),
    "bot_self_id": "10000",
    "adapter_name": "Milky",
    "provider_id": "openai",
    "model": "gpt-4o-mini",
    "prompt": "测试主题",
    "approval_mode": "never",
}


def _make_ctx(task_id: str = "t1", task_run_id: str = "r1", **overrides):
    from hoshino.ai.task.models import TaskContext

    data = {
        **_ctx_defaults,
        "task_id": task_id,
        "task_run_id": task_run_id,
        **overrides,
    }
    return TaskContext(**data)


def _create_task(
    tmp_store,
    *,
    task_id: str = "t1",
    creator_id: str = "42",
    kind: str = "research",
    ctx=None,
):
    """建一个最小 Task，返回 (task_id, task_run_id)。"""
    from hoshino.ai.task import events as task_events
    from hoshino.ai.task import store as task_store

    ctx = ctx or _make_ctx(task_id=task_id, creator_id=creator_id)
    created = task_store.create_task(
        task_id=task_id,
        kind=kind,
        prompt=ctx.prompt,
        scope_key=ctx.scope_key,
        creator_id=creator_id,
        target_json=ctx.target_json,
        provider_id=ctx.provider_id,
        model=ctx.model,
        context_json=json.dumps(ctx.to_json(), ensure_ascii=False),
        snapshot_json="{}",
        event_payloads=[
            {
                "event_type": task_events.CREATED,
                "payload": json.dumps({"kind": kind}),
            },
            {"event_type": task_events.QUEUED, "payload": "{}"},
        ],
        outbox_payloads=[
            {
                "event_type": task_events.CREATED,
                "sequence": 1,
                "payload": json.dumps({"kind": kind, "status": "accepted"}),
            }
        ],
    )
    assert "cooldown" not in created, created
    return created["task_id"], created["task_run_id"]
