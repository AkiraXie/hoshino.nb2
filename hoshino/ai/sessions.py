"""对话（上下文）管理器：内存优先 + SQLite write-through。

Session(scope) → Conversation 双层模型（plan aichat-context-timeout，对齐 AstrBot
ConversationManager）：每个 scope 持有多个命名对话，``active_conv_id`` 指向当前
对话；消息经 pydantic-ai ``ModelMessagesTypeAdapter`` 序列化。

- 读：内存命中直接用；miss 时惰性从 SQLite 载入并缓存（LRU 上限见 AIConfig）。
- 写：内存变更后立即 write-through 落库（每轮结束/创建/切换/清空）。所有持久化
  都是写穿，进程崩溃最多丢「进行中尚未落库的一轮」；LRU 逐出仅丢缓存。
- 每个 scope 一把 turn 锁：聊天轮次串行化；上层用 ``locked()`` 做忙检测。
  控制命令只动指针与内存，不占用忙锁。
"""

from __future__ import annotations

import asyncio
import time
from collections import OrderedDict
from dataclasses import dataclass, field

from pydantic_ai.messages import ModelMessage, ModelRequest, UserPromptPart

from . import context
from . import store

DEFAULT_CONVERSATION_NAME = "默认"


@dataclass
class Conversation:
    """一段命名对话的内存形态。历史由事件日志派生，``messages`` 是派生缓存。"""

    id: str
    scope_key: str
    name: str
    events: list[dict] = field(default_factory=list)
    provider_id: str = ""
    updated_at: float = 0.0
    _derived: list[ModelMessage] | None = field(default=None, init=False, repr=False)

    @property
    def messages(self) -> list[ModelMessage]:
        """从事件日志派生模型历史（惰性 + 缓存）。"""
        if self._derived is None:
            self._derived = context.derive_messages(self.events)
        return self._derived

    def _append_events(self, new_events: list[dict]) -> None:
        """追加事件并增量更新派生缓存。"""
        self.events.extend(new_events)
        if self._derived is not None:
            self._derived.extend(context.derive_messages(new_events))

    def _reset(self) -> None:
        self.events = []
        self._derived = []


@dataclass
class _ScopeChat:
    active_id: str | None = None
    # LRU 序：最近使用在尾部。
    convs: OrderedDict[str, Conversation] = field(default_factory=OrderedDict)


def _row_to_conversation(row: dict) -> Conversation:
    events = store.load_conversation_events(row["id"])
    legacy_json = row.get("messages_json") or ""
    if not events and legacy_json and legacy_json != "[]":
        # 旧数据惰性迁移：把 messages_json 折成事件（幂等、原子，规避并发双写）。
        legacy = context.messages_to_events(context.deserialize_messages(legacy_json))
        store.migrate_conv_events_if_empty(row["id"], legacy)
        events = store.load_conversation_events(row["id"])
    return Conversation(
        id=row["id"],
        scope_key=row["scope_key"],
        name=row["name"],
        events=events,
        provider_id=row["provider_id"],
        updated_at=row["updated_at"],
    )


def _run_log_prefix_events(run_log, provider_id: str) -> list[dict]:
    """把 RunLog 折成 log-only 前缀事件（request/header + turn/start + tool/call* + step/end*）。

    仅当 run_log 非空时产事件；空时返回 []，保持「无 run_log → 只写 surface 事件」的
    既有语义（迁移/测试路径不引入额外事件）。
    """
    if run_log is None:
        return []
    events: list[dict] = []
    if provider_id:
        events.append(
            {
                "type": context.EVENT_REQUEST_HEADER,
                "data": {"provider_id": provider_id},
            }
        )
    events.append(
        {"type": context.EVENT_TURN_START, "data": {"started_at": run_log.started_at}}
    )
    for call in run_log.tool_calls:
        events.append({"type": context.EVENT_TOOL_CALL, "data": call})
    for index, at in enumerate(run_log.step_at, 1):
        events.append(
            {"type": context.EVENT_STEP_END, "data": {"step": index, "at": at}}
        )
    return events


def _run_log_end_event(run_log, reason: str) -> dict:
    """RunLog 的 turn/end 事件；``reason`` 为 completed | timeout | max-requests 等。"""
    return {
        "type": context.EVENT_TURN_END,
        "data": {
            "reason": reason,
            "ended_at": run_log.ended_at,
            "steps": run_log.steps,
            "tool_count": len(run_log.tool_calls),
        },
    }


class ConversationManager:
    """单进程对话管理器。测试中可整体替换实例（经 ``sessions.conversation_manager``）。"""

    def __init__(self) -> None:
        self._scopes: OrderedDict[str, _ScopeChat] = OrderedDict()
        self._turn_locks: dict[str, asyncio.Lock] = {}

    # ------------------------------------------------------------------ 锁

    def turn_lock(self, scope_key: str) -> asyncio.Lock:
        lock = self._turn_locks.get(scope_key)
        if lock is None:
            lock = asyncio.Lock()
            self._turn_locks[scope_key] = lock
        return lock

    # ------------------------------------------------------------------ 读

    def _limits(self) -> tuple[int, int]:
        from .base import get_config

        config = get_config()
        return config.chat_memory_scopes, config.chat_memory_conversations

    def _get_state(self, scope_key: str) -> _ScopeChat:
        state = self._scopes.get(scope_key)
        if state is None:
            state = self._load_scope(scope_key)
            self._scopes[scope_key] = state
            self._evict_scopes_if_needed()
        else:
            self._scopes.move_to_end(scope_key)
        return state

    def _load_scope(self, scope_key: str) -> _ScopeChat:
        """从 SQLite 载入：active 对话 + 最近更新的对话（受 LRU 上限约束）。"""
        _, max_convs = self._limits()
        rows = store.get_conversations(scope_key)  # updated_at 倒序
        active_id = store.get_active_conv_id(scope_key)
        chosen: dict[str, Conversation] = {}
        for row in rows:
            if row["id"] == active_id or len(chosen) < max_convs:
                chosen[row["id"]] = _row_to_conversation(row)
        if active_id is not None and active_id not in chosen:
            row = store.get_conversation(active_id)
            if row is not None:
                chosen[active_id] = _row_to_conversation(row)
        convs = OrderedDict(
            (c.id, c) for c in sorted(chosen.values(), key=lambda c: c.updated_at)
        )
        if active_id not in convs:
            active_id = next(reversed(convs), None)
        return _ScopeChat(active_id=active_id, convs=convs)

    def get_active(self, scope_key: str) -> Conversation:
        """当前激活对话；指针失效回退最近更新者；全新 scope 自动建「默认」对话。"""
        state = self._get_state(scope_key)
        if state.active_id and state.active_id in state.convs:
            state.convs.move_to_end(state.active_id)
            return state.convs[state.active_id]
        if state.convs:
            conv = next(reversed(state.convs.values()))
            state.active_id = conv.id
            store.set_active_conv_id(scope_key, conv.id)
            return conv
        return self.create(scope_key)

    def find(self, scope_key: str, name: str) -> Conversation | None:
        state = self._get_state(scope_key)
        conv = next((c for c in state.convs.values() if c.name == name), None)
        if conv is not None:
            return conv
        row = store.find_conversation_by_name(scope_key, name)
        return _row_to_conversation(row) if row is not None else None

    def list_summaries(self, scope_key: str) -> list[dict]:
        """完整清单（以 DB 为准，含未驻留内存的对话），最近更新的在前。"""
        self._get_state(scope_key)  # 顺带预热缓存
        active_id = store.get_active_conv_id(scope_key)
        summaries = []
        for row in store.get_conversations(scope_key):
            # 消息条数 = surface 事件条数（log-only 事件不计）；未迁移的旧对话回退读 messages_json。
            count = store.count_conversation_events(
                row["id"], types=context.SURFACE_EVENT_TYPES
            )
            if count == 0 and row.get("messages_json"):
                count = len(context.deserialize_messages(row["messages_json"]))
            summaries.append(
                {
                    "id": row["id"],
                    "name": row["name"],
                    "count": count,
                    "updated_at": row["updated_at"],
                    "active": row["id"] == active_id,
                }
            )
        return summaries

    # ------------------------------------------------------------------ 写

    def create(self, scope_key: str, name: str | None = None) -> Conversation:
        """新建对话并激活；``name`` 缺省时自动命名（首个为「默认」，之后递增）。"""
        state = self._get_state(scope_key)
        final_name = self._resolve_new_name(scope_key, state, name)
        conv_id = store.new_conversation_id()
        store.create_conversation(scope_key, conv_id, final_name)
        store.set_active_conv_id(scope_key, conv_id)
        conv = Conversation(
            id=conv_id,
            scope_key=scope_key,
            name=final_name,
            updated_at=time.time(),
        )
        state.convs[conv_id] = conv
        state.active_id = conv_id
        self._evict_convs_if_needed(scope_key)
        return conv

    def _resolve_new_name(
        self, scope_key: str, state: _ScopeChat, name: str | None
    ) -> str:
        if name is not None:
            name = name.strip()
            if not name or any(ch.isspace() for ch in name):
                raise ValueError("对话名不能为空或包含空白。")
            if store.find_conversation_by_name(scope_key, name) is not None:
                raise ValueError(f"对话 `{name}` 已存在。")
            return name
        if not state.convs:
            return DEFAULT_CONVERSATION_NAME
        n = 1
        while store.find_conversation_by_name(scope_key, f"对话-{n}") is not None:
            n += 1
        return f"对话-{n}"

    def switch(self, scope_key: str, name: str) -> Conversation | None:
        """切到已存在的对话并激活；不存在返回 None。"""
        state = self._get_state(scope_key)
        conv = self.find(scope_key, name)
        if conv is None:
            return None
        if conv.id not in state.convs:
            state.convs[conv.id] = conv
            self._evict_convs_if_needed(scope_key)
        state.active_id = conv.id
        state.convs.move_to_end(conv.id)
        store.set_active_conv_id(scope_key, conv.id)
        return conv

    def clear_active(self, scope_key: str) -> bool:
        """清空当前对话事件（对话保留）；返回是否清掉了内容。"""
        conv = self.get_active(scope_key)
        had_content = bool(conv.messages)
        conv._reset()
        conv.updated_at = time.time()
        store.clear_conversation_events(conv.id)
        return had_content

    def commit_turn(
        self,
        scope_key: str,
        new_messages: list[ModelMessage],
        provider_id: str,
        run_log=None,
    ) -> None:
        """成功轮结束：把本轮新增消息折成事件 append（write-through）。

        ``run_log`` 非空时在 surface 事件前后追加 log-only 事件（request/header、
        turn/start、tool/call、step/end、turn/end）；空时只写 surface 事件。
        """
        conv = self.get_active(scope_key)
        events = _run_log_prefix_events(run_log, provider_id)
        events += context.messages_to_events(new_messages)
        if run_log is not None:
            events.append(_run_log_end_event(run_log, "completed"))
        conv._append_events(events)
        conv.provider_id = provider_id
        conv.updated_at = time.time()
        store.append_conversation_events(conv.id, events)
        store.update_conversation_provider(conv.id, provider_id)

    def append_prompt_only(
        self, scope_key: str, prompt: str, provider_id: str, run_log=None
    ) -> None:
        """超时/UsageLimit 超限：保留本轮提问为一条 user/message 事件，下一轮可续问。

        ``run_log`` 非空时同时落 log-only 事件（含超时前调用过的 tool/call），
        turn/end reason 取 ``run_log.reason``（timeout | max-requests）。
        """
        conv = self.get_active(scope_key)
        events = _run_log_prefix_events(run_log, provider_id)
        events += context.messages_to_events(
            [ModelRequest(parts=[UserPromptPart(content=prompt)])]
        )
        if run_log is not None:
            events.append(_run_log_end_event(run_log, run_log.reason or "aborted"))
        conv._append_events(events)
        conv.provider_id = provider_id
        conv.updated_at = time.time()
        store.append_conversation_events(conv.id, events)
        store.update_conversation_provider(conv.id, provider_id)

    # ------------------------------------------------------------------ LRU

    def _evict_scopes_if_needed(self) -> None:
        max_scopes, _ = self._limits()
        while len(self._scopes) > max_scopes:
            self._scopes.popitem(last=False)

    def _evict_convs_if_needed(self, scope_key: str) -> None:
        _, max_convs = self._limits()
        state = self._scopes.get(scope_key)
        if state is None:
            return
        while len(state.convs) > max_convs:
            for conv_id in list(state.convs):
                if conv_id != state.active_id:
                    del state.convs[conv_id]
                    break
            else:
                return

    # --------------------------------------------------------------- 生命周期

    def flush_all(self) -> None:
        """shutdown 兜底：事件 append 是同步写穿，无未落库内容，保留接口防未来惰性路径。"""


conversation_manager = ConversationManager()


def _register_lifecycle() -> None:
    from hoshino.core.hooks import on_shutdown

    @on_shutdown
    async def _flush_chat_contexts() -> None:
        conversation_manager.flush_all()


# 插件加载期（bootstrap 已 replay hooks）注册 shutdown flush；
# 测试环境 import 本模块不会触发真实 driver。
try:
    _register_lifecycle()
except Exception:  # pragma: no cover - 无 driver 的脚本环境
    pass
