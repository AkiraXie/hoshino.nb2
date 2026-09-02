"""Agent 运行时依赖（AgentDeps）与遥测 recorder。

chat 与 task 两个 surface 共用同一 ``AgentDeps`` 定义；``bot``/``event`` 是可选运行时
依赖（后台 Task 恢复时可能不可用）。只把每次 run
真正变化的状态注入 deps，固定的 store/logger/factory 不注入（设计审查结论）。

本模块只含类型与 Telemetry，不 ``require`` 插件——测试与 compaction/tools 可安全
顶层 import。依赖 alconna/uninfo 的构造函数见 ``deps_build``。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

from nonebot.adapters import Bot, Event

from . import metrics
from .config import AIConfig

if TYPE_CHECKING:
    # 唯一允许的延迟 import：类型专用（配合 from __future__ import annotations）。
    from nonebot_plugin_alconna.uniseg import Target

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
