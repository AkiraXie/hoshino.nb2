"""core/persona_manage：LLM 调用的人设管理工具。

领域 CRUD 在 ``persona.py``；本工具只解析参数、复核权限并调用领域函数（领域/入口分离）。
use/reset 需 ADMIN；global/delete 仅可通过 ``ai persona`` admin command 执行，工具内直接
拒绝并引导。list/show 无门槛。
"""

from __future__ import annotations

from typing import Literal

from pydantic_ai import RunContext

from ... import persona, store
from ...deps import AgentDeps

PersonaAction = Literal[
    "list", "show", "create", "update", "use", "reset", "global", "delete"
]


async def persona_manage(
    ctx: RunContext[AgentDeps],
    action: PersonaAction,
    name: str = "",
    gender: str = "",
    personality: str = "",
    description: str = "",
) -> str:
    """管理人设（persona）。

    - list：列出全部 persona
    - show <name>：查看详情与绑定情况
    - create <name> [性别/性格/简介]：创建（缺失特征会提示补充，可据此追问用户）
    - update <name> [性别/性格/简介]：更新特征并重新生成 prompt
    - use <name>：绑定当前会话为 scope 级 persona（需群管理员）
    - reset：解除当前会话绑定（需群管理员）
    - global <name>/off：设置/清除全局 persona（仅可通过 ai persona 管理员命令）
    - delete <name>：删除（仅可通过 ai persona 管理员命令）
    """
    perms = ctx.deps.permissions
    scope_key = ctx.deps.scope_key or ""
    is_privileged = perms.is_admin or perms.is_superuser

    if action == "list":
        rows = persona.list_personas()
        if not rows:
            return "暂无 persona。"
        return "\n".join(
            f"- {row['name']}：{row['description'] or row['prompt'][:40]}"
            for row in rows
        )

    if action == "show":
        if not name:
            return "show 需要 name 参数。"
        p = persona.get_persona(name)
        if p is None:
            return f"persona `{name}` 不存在。"
        return _format_detail(p, scope_key)

    if action in ("global", "delete"):
        return (
            "global/delete 仅可通过 `ai persona` 管理员命令执行，"
            "不能在对话中直接修改全局人设。"
        )

    if action == "create":
        if not name:
            return "create 需要 name 参数。"
        hint = persona.missing_traits(gender, personality, description)
        if hint:
            return hint
        try:
            p = persona.create_persona(
                name,
                gender=gender,
                personality=personality,
                description=description,
                created_by=perms.user_id or "",
            )
        except ValueError as exc:
            return str(exc)
        return f"已创建 persona `{p['name']}`：{p['prompt']}"

    if action == "update":
        if not name:
            return "update 需要 name 参数。"
        p = persona.update_persona(
            name,
            gender=gender or None,
            personality=personality or None,
            description=description or None,
        )
        if p is None:
            return f"persona `{name}` 不存在。"
        return f"已更新 persona `{p['name']}`：{p['prompt']}"

    if not is_privileged:
        return "use/reset 需要群管理员权限。"

    if action == "use":
        if not name:
            return "use 需要 name 参数。"
        if persona.bind_scope(scope_key, name, updated_by=perms.user_id or ""):
            return f"已绑定当前会话为 persona `{name}`。"
        return f"persona `{name}` 不存在。"

    if action == "reset":
        if persona.clear_scope(scope_key):
            return "已解除当前会话的 persona 绑定，回退默认。"
        return "当前会话没有绑定 persona。"

    return "未知操作。"


def _format_detail(p: dict, scope_key: str) -> str:
    lines = [f"persona `{p['name']}`", f"prompt：{p['prompt']}"]
    binds = []
    if scope_key and store.get_scope_persona_id(scope_key) == p["id"]:
        binds.append("当前 scope")
    if store.get_global_value("global_persona") == p["name"]:
        binds.append("全局")
    if binds:
        lines.append("绑定：" + "、".join(binds))
    return "\n".join(lines)
