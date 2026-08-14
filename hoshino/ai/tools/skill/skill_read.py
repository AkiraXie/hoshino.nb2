"""skill/skill_read：读取当前 scope 已启用技能的正文。"""

from __future__ import annotations

from pydantic_ai import RunContext

from ... import skills, store
from ...deps import AgentDeps


async def skill_read(ctx: RunContext[AgentDeps], skill_name: str) -> str:
    """读取指定技能的完整说明。

    只可读取当前 scope 已启用的技能；未启用或不存在会报错并列出可用技能。
    使用技能前必须先调用本工具读取完整说明，再按其指示执行。
    """
    scope_key = ctx.deps.scope_key or ""
    if not skill_name:
        return "skill_read 需要 skill_name 参数。"

    skill = skills.get_skill(skill_name)
    if skill is None:
        available = ", ".join(s.name for s in skills.list_skills()) or "（无）"
        return f"技能 `{skill_name}` 不存在。可用技能：{available}"

    if not store.get_skill_enabled(scope_key, skill_name):
        enabled = ", ".join(s.name for s in skills.list_enabled(scope_key)) or "（无）"
        return f"技能 `{skill_name}` 未启用。已启用的技能：{enabled}"

    return skill.body
