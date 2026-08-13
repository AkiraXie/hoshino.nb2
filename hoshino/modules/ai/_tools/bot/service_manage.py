"""bot/service_manage：管理本群 aichat 服务启停。需 live event + ADMIN。"""

from __future__ import annotations

from typing import Literal

from pydantic_ai import RunContext

from ..._deps import AgentDeps

ServiceAction = Literal["status", "enable", "disable"]


async def service_manage(
    ctx: RunContext[AgentDeps],
    action: ServiceAction = "status",
) -> str:
    """管理本群 AI 服务启停。

    - status：查看本群 aichat 服务是否启用
    - enable：启用本群服务（需群管理员）
    - disable：停用本群服务（需群管理员）

    仅作用于当前会话所在群/会话。
    """
    from ..._base import sv

    scope_key = ctx.deps.scope_key
    if not scope_key:
        return "无法解析当前 scope。"

    if action == "status":
        enabled = sv.check_enabled(scope_key)
        return f"本群 AI 服务{'已启用' if enabled else '未启用'}。"

    if action in ("enable", "disable"):
        if not (ctx.deps.permissions.is_admin or ctx.deps.permissions.is_superuser):
            return f"{action} 需要群管理员权限。"
        if action == "enable":
            sv.set_enable(scope_key)
        else:
            sv.set_disable(scope_key)
        return f"本群 AI 服务已{'启用' if action == 'enable' else '停用'}。"

    return "未知操作。"
