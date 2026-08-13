"""skill/skill_manage：启用/停用技能。enable/disable 需 ADMIN。"""

from __future__ import annotations

from typing import Literal

from pydantic_ai import RunContext

from ... import _skills as skills, _store as store
from ..._deps import AgentDeps

SkillAction = Literal["list", "enable", "disable"]


async def skill_manage(
    ctx: RunContext[AgentDeps],
    action: SkillAction = "list",
    skill_name: str = "",
) -> str:
    """管理技能启停。

    - list：列出全部技能及当前 scope 启停状态
    - enable <name>：启用（需群管理员）
    - disable <name>：停用（需群管理员）
    """
    scope_key = ctx.deps.scope_key or ""

    if action == "list":
        lines = ["可用技能："]
        for skill in skills.list_skills():
            mark = "✓" if store.get_skill_enabled(scope_key, skill.name) else "✗"
            lines.append(f"- {mark} `{skill.name}`：{skill.description or '无简介'}")
        return "\n".join(lines)

    if action in ("enable", "disable"):
        if not (ctx.deps.permissions.is_admin or ctx.deps.permissions.is_superuser):
            return f"{action} 需要群管理员权限。"
        if not skill_name:
            return f"{action} 需要 skill_name 参数。"
        enabled = action == "enable"
        if skills.set_enabled(scope_key, skill_name, enabled):
            return f"已{'启用' if enabled else '停用'}技能 `{skill_name}`。"
        return f"技能 `{skill_name}` 不存在。"

    return "未知操作。"
