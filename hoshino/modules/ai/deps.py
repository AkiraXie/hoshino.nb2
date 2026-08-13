"""Agent 运行时依赖（AgentDeps）与遥测 recorder。

chat 与 task 两个 surface 共用同一 ``AgentDeps`` 定义；``bot``/``event`` 是可选运行时
依赖（后台 Task 恢复时可能不可用，见 pydantic-ai-task-runtime-v1-plan.md）。只把每次 run
真正变化的状态注入 deps，固定的 store/logger/factory 不注入（设计审查结论）。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Literal

from nonebot.adapters import Bot, Event
from nonebot_plugin_alconna.uniseg import Target

from . import metrics
from .config import AIConfig

RuntimeSurface = Literal["chat", "task"]


@dataclass(frozen=True, slots=True)
class PermissionSnapshot:
    """创建/执行时刻的用户权限快照，供工具执行时复核（task 恢复时 bot 可能不可用）。"""

    user_id: str | None = None
    is_superuser: bool = False
    is_admin: bool = False


@dataclass(frozen=True, slots=True)
class AgentDeps:
    surface: RuntimeSurface
    scope_key: str | None
    target: Target
    config: AIConfig
    permissions: PermissionSnapshot
    bot: Bot | None
    event: Event | None
    telemetry: Telemetry
    # Task 阶段注入 TaskContext；基础阶段（chat）恒为 None。
    task: Any | None = None


@dataclass(slots=True)
class Telemetry:
    """每次请求一个实例注入 deps；请求结束后由 chat/task 调用 record_* 落库。"""

    provider_id: str
    scope_key: str
    model: str
    _start: float = field(default_factory=time.perf_counter)

    def record_success(self, result) -> None:
        metrics.record_success(
            provider_id=self.provider_id,
            scope_key=self.scope_key,
            model=self.model,
            snapshot=metrics.snapshot_from_result(result),
            latency_ms=(time.perf_counter() - self._start) * 1000,
        )

    def record_error(self, error: str) -> None:
        metrics.record_error(
            provider_id=self.provider_id,
            scope_key=self.scope_key,
            model=self.model,
            latency_ms=(time.perf_counter() - self._start) * 1000,
            error=error,
        )


async def build_permission_snapshot(bot: Bot, event: Event) -> PermissionSnapshot:
    """从当前事件构造权限快照。uninfo 解析失败时退化为仅 SUPERUSER 判断。"""
    from hoshino.platform.event import get_user_id
    from hoshino.platform.superuser import is_superuser

    user_id = get_user_id(event)
    uid = str(user_id) if user_id is not None else None
    is_super = bool(uid is not None and is_superuser(bot, user_id))
    is_admin = is_super
    if uid is not None:
        try:
            from nonebot_plugin_uninfo import get_session

            session = await get_session(bot=bot, event=event)
            role = session.member.role if session and session.member else ""
            if role in ("admin", "owner"):
                is_admin = True
        except Exception:
            pass
    return PermissionSnapshot(user_id=uid, is_superuser=is_super, is_admin=is_admin)


def construct_chat_deps(
    bot: Bot,
    event: Event,
    config: AIConfig,
    permissions: PermissionSnapshot,
    *,
    provider_id: str,
    model: str,
) -> AgentDeps:
    """构造即时聊天 surface 的 AgentDeps。"""
    from hoshino.platform import event_scope_key, target_from_event

    scope_key = event_scope_key(bot, event)
    return AgentDeps(
        surface="chat",
        scope_key=scope_key,
        target=target_from_event(bot, event),
        config=config,
        permissions=permissions,
        bot=bot,
        event=event,
        telemetry=Telemetry(
            provider_id=provider_id,
            scope_key=scope_key or "",
            model=model,
        ),
    )
