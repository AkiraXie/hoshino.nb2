"""core/provider_choose：超级用户调整当前 scope 的 provider / 文本模型 / 视觉模型。

把 ``ai provider use`` / ``ai model set text|vision`` 等管理员命令的语义做成 LLM
工具：superuser 可以直接让模型帮自己切换 provider、设定文本/视觉模型（含校验
model-list 与多模态能力）。非超级用户调用一律拒绝。

只写 scope 级覆盖（``ai_scope_providers`` / ``ai_scope_models``），不动全局默认。
"""

from __future__ import annotations

from typing import Literal

from pydantic_ai import RunContext

from ... import provider, store
from ...deps import AgentDeps

ProviderAction = Literal["status", "provider", "text", "vision", "reset"]


def _effective_provider_id(ctx: RunContext[AgentDeps]) -> str:
    """当前 scope 的有效 provider id（scope 绑定 > 配置默认）；无则空串。"""
    scope_key = ctx.deps.scope_key or ""
    bound = store.get_scope_provider(scope_key)
    if bound and provider.has_provider(bound):
        return bound
    default = ctx.deps.config.default
    return default if default and provider.has_provider(default) else ""


def _status_text(ctx: RunContext[AgentDeps], pid: str) -> str:
    scope_key = ctx.deps.scope_key or ""
    lines = [f"当前 scope：`{scope_key or '（未绑定）'}`"]
    if not pid:
        lines.append("没有可用 provider（scope 未绑定且无默认）。")
        return "\n".join(lines)
    bound = store.get_scope_provider(scope_key)
    lines.append(f"provider：`{pid}`" + ("（scope 绑定）" if bound else "（默认）"))
    text_model, vision_model = provider.resolve_models(scope_key, pid)
    lines.append(f"纯文本模型：`{text_model or '（未配置）'}`")
    lines.append(f"视觉模型：`{vision_model or '（无，无法看图）'}`")
    models = provider.list_models(pid)
    if models:
        cap = {"text": "文本", "multimodal": "多模态", "both": "文本+多模态"}
        lines.append(
            "该 provider 可用模型："
            + "；".join(
                f"`{m['model']}`（{cap.get(m['capabilities'], m['capabilities'])}）"
                for m in models
            )
        )
    return "\n".join(lines)


async def provider_choose(
    ctx: RunContext[AgentDeps],
    action: ProviderAction,
    value: str = "",
) -> str:
    """管理当前会话的 provider / 文本模型 / 视觉模型（仅超级用户可用）。

    - status：查看当前 provider 与生效的文本/视觉模型、可用模型清单
    - provider <id>：把当前会话切换到指定 provider
    - text <model>：设置文本模型（须在 provider 的 model-list 中）
    - vision <model>：设置视觉（多模态）模型（须注册为 multimodal）
    - vision none：显式禁用多模态
    - reset [text|vision]：清除模型覆盖，回退 provider 默认
    """
    if not ctx.deps.permissions.is_superuser:
        return "该工具仅超级用户可用（superuser），当前用户无权限。"
    scope_key = ctx.deps.scope_key or ""
    actor = ctx.deps.permissions.user_id or ""

    if action == "status":
        return _status_text(ctx, _effective_provider_id(ctx))

    if action == "provider":
        if not value:
            return "用法：provider <id>（可用 id 见 status 或 `ai provider list`）。"
        if not provider.has_provider(value):
            return f"provider `{value}` 不存在。"
        store.set_scope_provider(scope_key, value, updated_by=actor)
        return f"已把当前会话切换到 provider `{value}`。"

    pid = _effective_provider_id(ctx)
    if not pid:
        return "当前会话没有可用 provider，请先 `provider <id>` 或联系管理员配置。"

    if action == "text":
        if not value:
            return "用法：text <model>。"
        error = provider.validate_model_choice(pid, value, "text")
        if error:
            return error
        store.set_scope_model_override(scope_key, "text", value, updated_by=actor)
        return f"已把文本模型设为 `{value}`（覆盖 provider 默认）。"

    if action == "vision":
        if not value:
            return "用法：vision <model>（或 vision none 禁用）。"
        if value == "none":
            store.set_scope_model_override(
                scope_key, "vision", "none", updated_by=actor
            )
            return "已显式禁用多模态（vision）。"
        error = provider.validate_model_choice(pid, value, "vision")
        if error:
            return error
        store.set_scope_model_override(scope_key, "vision", value, updated_by=actor)
        return f"已把视觉模型设为 `{value}`（覆盖 provider 默认）。"

    if action == "reset":
        if value and value not in ("text", "vision"):
            return "用法：reset [text|vision]。"
        slot = value or None
        store.clear_scope_model_override(scope_key, slot)
        return "已清除模型覆盖，回退 provider 默认。"

    return "未知 action，可用：status / provider / text / vision / reset。"
