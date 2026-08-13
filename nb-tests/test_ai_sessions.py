"""多对话（上下文）管理单元测试：ConversationManager / 按轮截断 / 会话迁移。

不连接真实模型；manager 用 tmp_store 指向的临时 SQLite 验证 write-through 与迁移。
"""

from __future__ import annotations

import pytest
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)

from hoshino.modules.ai import _context, _runner, _sessions
from hoshino.modules.ai._config import AIConfig

pytestmark = pytest.mark.usefixtures("_clear_uninfo_cache")


@pytest.fixture
def manager():
    return _sessions.ConversationManager()


def _user(text: str) -> ModelRequest:
    return ModelRequest(parts=[UserPromptPart(content=text)])


def _asst(text: str) -> ModelResponse:
    return ModelResponse(parts=[TextPart(text)])


# ------------------------------------------------------------- 基本操作


def test_get_active_auto_creates_default(manager, tmp_store):
    conv = manager.get_active("milky:1")
    assert conv.name == "默认"
    assert manager.get_active("milky:1") is conv


def test_create_activates_and_auto_names(manager, tmp_store):
    manager.get_active("milky:1")
    c1 = manager.create("milky:1")
    assert c1.name == "对话-1"
    assert manager.get_active("milky:1").id == c1.id
    c2 = manager.create("milky:1")
    assert c2.name == "对话-2"


def test_create_rejects_whitespace_and_duplicate(manager, tmp_store):
    manager.get_active("milky:1")
    with pytest.raises(ValueError, match="空白"):
        manager.create("milky:1", "a b")
    with pytest.raises(ValueError, match="为空"):
        manager.create("milky:1", "   ")
    manager.create("milky:1", "甲")
    with pytest.raises(ValueError, match="已存在"):
        manager.create("milky:1", "甲")


def test_switch_and_missing(manager, tmp_store):
    manager.get_active("milky:1")
    manager.create("milky:1", "甲")
    conv = manager.switch("milky:1", "默认")
    assert conv is not None and conv.name == "默认"
    assert manager.get_active("milky:1").name == "默认"
    assert manager.switch("milky:1", "幽灵") is None


def test_clear_active_keeps_conversation(manager, tmp_store):
    conv = manager.get_active("milky:1")
    manager.append_prompt_only("milky:1", "hi", "openai")
    assert manager.clear_active("milky:1") is True
    assert manager.clear_active("milky:1") is False
    assert manager.get_active("milky:1").id == conv.id
    assert manager.get_active("milky:1").messages == []


def test_list_summaries_active_and_count(manager, tmp_store):
    manager.get_active("milky:1")
    manager.append_prompt_only("milky:1", "hi", "openai")
    manager.create("milky:1", "甲")
    summaries = manager.list_summaries("milky:1")
    by_name = {s["name"]: s for s in summaries}
    assert by_name["甲"]["active"] is True
    assert by_name["默认"]["active"] is False
    assert by_name["默认"]["count"] == 1


# ----------------------------------------------------------- write-through


def test_commit_turn_persists_across_manager_rebuild(manager, tmp_store):
    messages = [_user("问题"), _asst("回答")]
    manager.get_active("milky:1")
    manager.commit_turn("milky:1", messages, "openai")

    fresh = _sessions.ConversationManager()
    conv = fresh.get_active("milky:1")
    assert conv.name == "默认"
    assert len(conv.messages) == 2
    assert conv.provider_id == "openai"


def test_append_prompt_only_persists(manager, tmp_store):
    manager.get_active("milky:1")
    manager.append_prompt_only("milky:1", "超时的问题", "openai")
    fresh = _sessions.ConversationManager()
    conv = fresh.get_active("milky:1")
    assert len(conv.messages) == 1
    assert isinstance(conv.messages[0].parts[0], UserPromptPart)


# ------------------------------------------------------------------- LRU


def test_lru_evicts_non_active(monkeypatch, tmp_store):
    """驻留上限内只保留 active + 最近对话；写穿策略下逐出仅丢缓存。"""
    from hoshino.modules.ai import _base

    monkeypatch.setattr(
        _base, "get_config", lambda: AIConfig(chat_memory_conversations=2)
    )
    manager = _sessions.ConversationManager()
    manager.get_active("milky:1")  # 默认
    manager.create("milky:1", "甲")
    manager.create("milky:1", "乙")
    manager.create("milky:1", "丙")

    state = manager._scopes["milky:1"]
    assert len(state.convs) <= 2
    assert state.active_id in state.convs
    # DB 里四个对话都在（写穿，逐出只丢内存）
    assert len(tmp_store.get_conversations("milky:1")) == 4
    # 逐出的对话仍可按名切回（从 DB 惰性载入）
    conv = manager.switch("milky:1", "默认")
    assert conv is not None


# ---------------------------------------------------------------- 迁移


def test_migrate_sessions_to_conversations(tmp_store):
    tmp_store.save_session_messages("milky:old", '[{"kind":"request"}]', "openai")
    tmp_store.migrate_sessions_to_conversations(tmp_store.engine)

    convs = tmp_store.get_conversations("milky:old")
    assert len(convs) == 1
    assert convs[0]["name"] == "默认"
    assert convs[0]["provider_id"] == "openai"
    assert tmp_store.get_active_conv_id("milky:old") == convs[0]["id"]

    # 幂等：二次执行不重复迁移
    tmp_store.migrate_sessions_to_conversations(tmp_store.engine)
    assert len(tmp_store.get_conversations("milky:old")) == 1

    # 已有对话的 scope 不受旧表影响
    manager = _sessions.ConversationManager()
    manager.get_active("milky:new")
    tmp_store.save_session_messages("milky:new", "[]", "x")
    tmp_store.migrate_sessions_to_conversations(tmp_store.engine)
    assert len(tmp_store.get_conversations("milky:new")) == 1


# ------------------------------------------------------------- 按轮截断


def _tool_round(question: str, answer: str) -> list:
    return [
        _user(question),
        ModelResponse(
            parts=[ToolCallPart(tool_name="now", args={}, tool_call_id="c1")]
        ),
        ModelRequest(
            parts=[ToolReturnPart(tool_name="now", content="ok", tool_call_id="c1")]
        ),
        _asst(answer),
    ]


def test_truncate_keeps_round_boundaries():
    messages = [
        _user("q1"),
        _asst("a1"),
        *_tool_round("q2", "a2"),
        _user("q3"),
        _asst("a3"),
    ]
    # 切点落在工具轮内部（cut=3）→ 对齐到 q3 的轮边界，宁可多丢
    kept = _context.truncate_messages(messages, 5)
    assert len(kept) == 2
    assert kept[0].parts[0].content == "q3"
    assert kept[1].parts[0].content == "a3"
    # 切点=2 正好是工具轮边界 → 完整保留工具轮
    kept = _context.truncate_messages(messages, 6)
    assert kept[0].parts[0].content == "q2"
    assert len(kept) == 6


def test_truncate_never_splits_overlong_last_round():
    messages = _tool_round("q", "a")  # 一轮 4 条
    kept = _context.truncate_messages(messages, 2)
    assert len(kept) == 4  # 最后一轮超长时整轮保留，不切半轮


def test_truncate_passthrough_and_fallback():
    messages = [_user("q1"), _asst("a1")]
    assert _context.truncate_messages(messages, 0) is not messages
    assert len(_context.truncate_messages(messages, 0)) == 2
    assert len(_context.truncate_messages(messages, 10)) == 2
    # 无轮可对齐的异常历史退化为尾部保留
    orphan = [_asst("x"), _asst("y"), _asst("z")]
    kept = _context.truncate_messages(orphan, 2)
    assert [m.parts[0].content for m in kept] == ["y", "z"]


# ------------------------------------------------------- 事件日志（append-only）


def test_messages_to_events_derive_roundtrip():
    """messages_to_events → derive_messages 无损往返（含工具轮，可重放）。"""
    messages = _tool_round("q", "a")
    events = _context.messages_to_events(messages)
    derived = _context.derive_messages(events)
    assert _context.serialize_messages(derived) == _context.serialize_messages(messages)


def test_derive_skips_unknown_event_types():
    """未知事件类型在派生时跳过，不破坏重放（前向兼容）。"""
    events = [
        {"type": _context.EVENT_USER_MESSAGE, "data": {"content": "hi"}},
        {"type": "future/event", "data": {"x": 1}},
        {
            "type": _context.EVENT_ASSISTANT_MESSAGE,
            "data": {"message_json": _context.serialize_message(_asst("ok"))},
        },
    ]
    derived = _context.derive_messages(events)
    assert len(derived) == 2
    assert derived[0].parts[0].content == "hi"


def test_events_appended_not_overwritten(manager, tmp_store):
    """连续两轮只追加事件，不覆盖旧历史（append-only）。"""
    manager.get_active("milky:1")
    manager.commit_turn("milky:1", [_user("q1"), _asst("a1")], "openai")
    manager.commit_turn("milky:1", [_user("q2"), _asst("a2")], "openai")

    conv = manager.get_active("milky:1")
    assert [m.parts[0].content for m in conv.messages] == ["q1", "a1", "q2", "a2"]

    events = tmp_store.load_conversation_events(conv.id)
    assert [e["type"] for e in events] == [
        "user/message",
        "assistant/message",
        "user/message",
        "assistant/message",
    ]
    # seq 连续
    assert [e["seq"] for e in events] == [0, 1, 2, 3]


def test_replay_across_manager_rebuild_with_tools(manager, tmp_store):
    """重建 manager 后从事件日志重放，含工具轮完整还原（可恢复 + 可重放）。"""
    manager.get_active("milky:1")
    messages = _tool_round("问题", "回答")
    manager.commit_turn("milky:1", messages, "openai")

    fresh = _sessions.ConversationManager()
    conv = fresh.get_active("milky:1")
    assert _context.serialize_messages(conv.messages) == _context.serialize_messages(
        messages
    )


def test_clear_active_removes_events(manager, tmp_store):
    manager.get_active("milky:1")
    manager.commit_turn("milky:1", [_user("q"), _asst("a")], "openai")
    conv = manager.get_active("milky:1")
    assert tmp_store.count_conversation_events(conv.id) == 2
    assert manager.clear_active("milky:1") is True
    assert tmp_store.count_conversation_events(conv.id) == 0
    assert manager.get_active("milky:1").messages == []


def test_append_prompt_only_as_event(manager, tmp_store):
    manager.get_active("milky:1")
    manager.append_prompt_only("milky:1", "超时的问题", "openai")
    conv = manager.get_active("milky:1")
    events = tmp_store.load_conversation_events(conv.id)
    assert [e["type"] for e in events] == ["user/message"]
    assert events[0]["data"]["content"] == "超时的问题"

    fresh = _sessions.ConversationManager()
    assert len(fresh.get_active("milky:1").messages) == 1


def test_legacy_messages_json_migrates_to_events(tmp_store):
    """旧 messages_json 在加载期惰性迁移为事件（幂等，不重复）。"""
    from hoshino.modules.ai import _store as store

    store.create_conversation("milky:legacy", "c_legacy", "默认")
    store.save_conversation_messages(
        "c_legacy",
        _context.serialize_messages([_user("旧问题"), _asst("旧回答")]),
        "openai",
    )
    store.set_active_conv_id("milky:legacy", "c_legacy")

    manager = _sessions.ConversationManager()
    conv = manager.get_active("milky:legacy")
    assert [m.parts[0].content for m in conv.messages] == ["旧问题", "旧回答"]
    assert len(store.load_conversation_events("c_legacy")) == 2

    # 再次载入不重复迁移
    fresh = _sessions.ConversationManager()
    assert len(fresh.get_active("milky:legacy").messages) == 2
    assert len(store.load_conversation_events("c_legacy")) == 2


# ------------------------------------------------------- log-only 事件


def _make_run_log(**kwargs) -> "_runner.RunLog":
    run_log = _runner.RunLog(started_at=1.0, ended_at=2.0, steps=1, step_at=[1.5])
    for key, value in kwargs.items():
        setattr(run_log, key, value)
    return run_log


def test_commit_turn_with_run_log_writes_log_only_events(manager, tmp_store):
    """run_log 非空时：surface 事件前后追加 log-only 事件，派生历史不受影响。"""
    manager.get_active("milky:1")
    run_log = _make_run_log()
    run_log.tool_calls.append({"name": "now", "args_summary": "{}"})
    messages = [_user("q"), _asst("a")]
    manager.commit_turn("milky:1", messages, "openai", run_log)

    conv = manager.get_active("milky:1")
    events = tmp_store.load_conversation_events(conv.id)
    assert [e["type"] for e in events] == [
        "request/header",
        "turn/start",
        "tool/call",
        "step/end",
        "user/message",
        "assistant/message",
        "turn/end",
    ]
    assert events[-1]["data"]["reason"] == "completed"
    # 派生只含 surface，log-only 被跳过
    assert [m.parts[0].content for m in conv.messages] == ["q", "a"]

    # 重建 manager 后重放仍一致（log-only 不影响重放）
    fresh = _sessions.ConversationManager()
    assert _context.serialize_messages(
        fresh.get_active("milky:1").messages
    ) == _context.serialize_messages(messages)


def test_append_prompt_only_with_run_log_keeps_tool_calls(manager, tmp_store):
    """超时路径保留提问的同时，记录超时前调用过的工具与 turn/end reason。"""
    manager.get_active("milky:1")
    run_log = _make_run_log(reason="timeout")
    run_log.tool_calls.append({"name": "web_search", "args_summary": "q=<3>"})
    manager.append_prompt_only("milky:1", "超时问题", "openai", run_log)

    conv = manager.get_active("milky:1")
    events = tmp_store.load_conversation_events(conv.id)
    types = [e["type"] for e in events]
    assert "tool/call" in types
    assert types[-1] == "turn/end"
    assert events[-1]["data"]["reason"] == "timeout"
    assert events[-1]["data"]["tool_count"] == 1
    # surface 只含提问
    assert [m.parts[0].content for m in conv.messages] == ["超时问题"]


def test_list_summaries_counts_surface_only(manager, tmp_store):
    """log-only 事件不计入 #list 的消息条数。"""
    manager.get_active("milky:1")
    run_log = _make_run_log()
    manager.commit_turn("milky:1", [_user("q"), _asst("a")], "openai", run_log)

    summaries = manager.list_summaries("milky:1")
    assert summaries[0]["count"] == 2  # 只数 user/message + assistant/message
