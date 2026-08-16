"""工具注册表与动态解析。

``ToolRegistration`` 集中工具元数据：tool_id/version、分类、surface、风险基线、live-event
依赖与本地访问标记。模型是否“看见工具”由 ``resolve_tools`` 过滤决定；工具执行函数仍必须在
执行时复核 scope、权限、路径与 live runtime（授权与注入分离，见计划设计审查结论 6）。

web 类别复用 pydantic-ai common_tools 的 ``Tool``；其余导出纯函数，由 ``FunctionToolset``
推断 schema 与 ``takes_ctx``。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from pydantic_ai import Tool

from .. import prompts, skills, store
from ..deps import AgentDeps
from .bot import send_message as _send_message
from .bot import service_manage as _service_manage
from .computer import bash as _bash
from .computer import file as _file
from .computer import python as _python
from .computer import repo_code as _repo_code
from .core import image_view as _image_view
from .core import memory as _memory
from .core import now as _now
from .core import persona_manage as _persona_manage
from .core import provider_choose as _provider_choose
from .skill import skill_manage as _skill_manage
from .skill import skill_read as _skill_read
from .web import browser_use as _browser_use
from .web import web_fetch as _web_fetch
from .web import web_search as _web_search

ToolCategory = Literal["core", "computer", "bot", "web", "skill"]
RiskLevel = Literal["low", "medium", "high"]
Surface = Literal["chat", "task"]

# scope 从未配置过工具类别时的安全默认：core/web/skill 可用。
_DEFAULT_CATEGORIES: frozenset[str] = frozenset({"core", "web", "skill"})


@dataclass(frozen=True, slots=True)
class ToolRegistration:
    tool_id: str
    version: int
    tool: Tool | Callable[..., Any] | None
    category: ToolCategory
    surfaces: frozenset[Surface]
    risk: RiskLevel = "low"
    risk_for: Callable[[dict[str, Any]], RiskLevel] | None = None
    requires_live_event: bool = False
    local_access: bool = False


REGISTRATIONS: tuple[ToolRegistration, ...] = (
    ToolRegistration("now", 1, _now.now, "core", frozenset({"chat", "task"})),
    ToolRegistration(
        "memory",
        1,
        _memory.memory,
        "core",
        frozenset({"chat", "task"}),
        risk="medium",
    ),
    ToolRegistration(
        "persona_manage",
        1,
        _persona_manage.persona_manage,
        "core",
        frozenset({"chat", "task"}),
        risk="medium",
    ),
    ToolRegistration(
        "provider_choose",
        1,
        _provider_choose.provider_choose,
        "core",
        frozenset({"chat", "task"}),
        risk="medium",
    ),
    ToolRegistration(
        "bash",
        1,
        _bash.bash,
        "computer",
        frozenset({"chat", "task"}),
        risk="high",
        local_access=True,
    ),
    ToolRegistration(
        "python",
        1,
        _python.python,
        "computer",
        frozenset({"chat", "task"}),
        risk="high",
        local_access=True,
    ),
    ToolRegistration(
        "file",
        1,
        _file.file,
        "computer",
        frozenset({"chat", "task"}),
        risk="medium",
        risk_for=_file.risk_for_file,
        local_access=True,
    ),
    ToolRegistration(
        "hoshino_nb2_code",
        1,
        _repo_code.hoshino_nb2_code,
        "computer",
        frozenset({"chat", "task"}),
        risk="low",
        local_access=True,
    ),
    ToolRegistration(
        "service_manage",
        1,
        _service_manage.service_manage,
        "bot",
        frozenset({"chat"}),
        risk="medium",
        requires_live_event=True,
    ),
    ToolRegistration(
        "send_message",
        1,
        _send_message.send_message,
        "bot",
        frozenset({"chat"}),
        risk="medium",
        requires_live_event=True,
    ),
    ToolRegistration(
        "web_search",
        1,
        _web_search.tool,
        "web",
        frozenset({"chat", "task"}),
    ),
    ToolRegistration(
        "web_fetch",
        1,
        _web_fetch.tool,
        "web",
        frozenset({"chat", "task"}),
    ),
    ToolRegistration(
        "image_view",
        1,
        _image_view.tool,
        "core",
        frozenset({"chat", "task"}),
    ),
    ToolRegistration(
        "browser_use",
        1,
        _browser_use.tool,
        "web",
        frozenset({"chat", "task"}),
        risk="medium",
        local_access=True,
    ),
    ToolRegistration(
        "skill_read",
        1,
        _skill_read.skill_read,
        "skill",
        frozenset({"chat", "task"}),
    ),
    ToolRegistration(
        "skill_manage",
        1,
        _skill_manage.skill_manage,
        "skill",
        frozenset({"chat"}),
        risk="medium",
    ),
)


def _enabled_categories(scope_key: str, surface: str) -> frozenset[str]:
    """解析 scope 的启用类别：默认 core/web/skill，显式 ``on`` 叠加、``off`` 移除。

    叠加语义（而非"有显式行就整体替换默认"）：只开 computer 时基础/联网/技能
    仍保留，显式关闭某项才从默认中移除。
    """
    enabled = set(_DEFAULT_CATEGORIES)
    for binding in store.list_scope_tool_bindings(scope_key, surface):
        if binding["enabled"]:
            enabled.add(binding["category"])
        else:
            enabled.discard(binding["category"])
    return frozenset(enabled)


def resolve_tools(deps: AgentDeps) -> list[Tool | Callable[..., Any]]:
    """按 surface、scope binding 和 runtime capability 解析工具。

    - Task 恢复：只按 Task 冻结的 ``tool_profile`` 展开，不能用当前 category 重新展开。
    - chat：category 绑定（默认 core/web/skill，显式行叠加/移除）+ surface +
      live-event 依赖过滤。
    """
    if deps.task is not None:
        return [
            item.tool
            for item in REGISTRATIONS
            if item.tool is not None and (item.tool_id, item.version) in deps.task.tool_profile
        ]

    scope_key = deps.scope_key or ""
    enabled_categories = _enabled_categories(scope_key, deps.surface)

    result: list[Tool | Callable[..., Any]] = []
    for item in REGISTRATIONS:
        if item.tool is None:
            continue
        if deps.surface not in item.surfaces:
            continue
        if item.category not in enabled_categories:
            continue
        if item.requires_live_event and deps.event is None:
            continue
        # 静态 high-risk 的 shell/Python 不注入 chat；file 的参数级高风险由工具内部拒绝。
        if deps.surface == "chat" and item.risk == "high":
            continue
        result.append(item.tool)
    return result


def tool_category(tool) -> str:
    """反查一个已解析工具的类别名（供管理展示按类别分组）。"""
    for reg in REGISTRATIONS:
        if reg.tool is tool:
            return reg.category
    return "?"


def build_tool_instructions(deps: AgentDeps) -> list[str]:
    """组装动态 toolset 的 instructions；无工具/无技能时返回空列表（persona 不污染）。"""
    parts: list[str] = []
    if resolve_tools(deps):
        parts.append(prompts.TOOL_CALL_PROMPT)
    enabled_skills = skills.list_enabled(deps.scope_key or "")
    if enabled_skills:
        parts.append(prompts.build_skills_prompt(enabled_skills))
    return parts


def enabled_task_categories(scope_key: str) -> list[str]:
    """scope 在 task surface 的启用类别（capability snapshot 冻结用）。

    与 ``resolve_tools``/``freeze_tool_profile`` 同一叠加语义：默认 + 显式 on − 显式 off。
    """
    return sorted(_enabled_categories(scope_key, "task"))


def freeze_tool_profile(scope_key: str) -> dict[str, int]:
    """按 scope 的 task binding 展开最终 tool_id -> version profile（Task 冻结用）。

    与 ``resolve_tools`` 同一 category 解析，但展开为可持久化的 id/version 快照；
    Task 恢复只按该快照展开，不受后续 binding 变化影响。
    """
    enabled_categories = _enabled_categories(scope_key, "task")
    profile: dict[str, int] = {}
    for reg in REGISTRATIONS:
        if reg.tool is None:
            continue
        if "task" not in reg.surfaces:
            continue
        if reg.category not in enabled_categories:
            continue
        profile[reg.tool_id] = reg.version
    return profile


def _tool_risk(tool_name: str, kwargs: dict[str, Any]) -> RiskLevel:
    """按 ToolRegistration 反查工具风险；risk_for 参数级判定优先。"""
    for reg in REGISTRATIONS:
        if reg.tool is None:
            continue
        name = getattr(reg.tool, "name", None) or getattr(reg.tool, "__name__", None)
        if name == tool_name or reg.tool_id == tool_name:
            if reg.risk_for is not None:
                try:
                    return reg.risk_for(kwargs)
                except Exception:
                    return reg.risk
            return reg.risk
    return "low"


def approval_required(ctx, tool_definition, kwargs: dict[str, Any]) -> bool:
    """ApprovalRequiredToolset 回调：决定一次 tool call 是否需要 deferred approval。

    - chat（task 为空）从不审批：high-risk 工具已静态排除，file 参数级高风险返回
      “创建 Task”的无副作用结果（chat 不使用 deferred approval）；
    - task 按冻结 approval_mode：never 不审批；always 全部审批；auto 仅 high-risk。
    """
    task = getattr(ctx.deps, "task", None)
    if task is None:
        return False
    mode = getattr(task, "approval_mode", "auto")
    if mode == "never":
        return False
    if mode == "always":
        return True
    return _tool_risk(tool_definition.name, kwargs) == "high"
