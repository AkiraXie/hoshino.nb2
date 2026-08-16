"""core/provider_choose：超级用户调整当前 scope 的 provider / 文本模型 / vision。

把 ``ai provider set`` / ``ai model set`` / ``ai vision set`` 等管理员命令的语义
做成 LLM 工具：superuser 可以直接让模型帮自己切换 provider、设定文本模型与
vision（独立 provider + 模型）。可用模型一律调用 provider API 实时获取校验
（本地不维护 model-list）。

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


async def _available_models(ctx: RunContext[AgentDeps], pid: str) -> list[str] | None:
    """实时获取 provider 的可用模型；失败返回 None。"""
    record = provider.get_provider(pid)
    if record is None:
        return None
    return await provider.fetch_available_models(
        record,
        proxy=provider.resolve_effective_proxy(record, ctx.deps.config.proxy),
        verify=ctx.deps.config.web_fetch_verify_ssl,
    )


async def _status_text(ctx: RunContext[AgentDeps], pid: str) -> str:
    scope_key = ctx.deps.scope_key or ""
    lines = [f"当前 scope：`{scope_key or '（未绑定）'}`"]
    if not pid:
        lines.append("没有可用 provider（scope 未绑定且无默认）。")
        return "\n".join(lines)
    bound = store.get_scope_provider(scope_key)
    lines.append(f"provider：`{pid}`" + ("（scope 绑定）" if bound else "（默认）"))
    text_model = provider.resolve_text_model(scope_key, pid)
    lines.append(f"纯文本模型：`{text_model or '（未配置）'}`")
    vision_pid, vision_model = provider.resolve_vision(scope_key)
    if vision_model:
        lines.append(f"vision：`{vision_pid}` / `{vision_model}`")
    else:
        lines.append("vision：`（未配置，无法看图）`")
    models = await _available_models(ctx, pid)
    if models:
        lines.append("该 provider 可用模型（API 实时获取）：" + "、".join(f"`{m}`" for m in models))
    else:
        lines.append("可用模型获取失败（网络或端点不支持）。")
    return "\n".join(lines)


async def _validate_model(ctx: RunContext[AgentDeps], pid: str, model: str) -> tuple[bool, str]:
    """实时校验模型：返回 (ok, 附加信息)。网络失败放行并附警告。"""
    available = await _available_models(ctx, pid)
    if available is None:
        return True, "（无法连接 provider 校验，已直接设置）"
    if model not in available:
        return False, f"模型 `{model}` 不在该 provider 的 API 可用列表中。"
    return True, ""


def _parse_vision_spec(value: str) -> tuple[str, str] | None:
    """解析 ``provider/model`` 或 ``provider model`` 为 (provider, model)。

    斜杠形式按第一个 ``/`` 切分（模型名可含 ``/``，如 ``org/model``）。
    """
    if "/" in value:
        pid, _, model = value.partition("/")
        return (pid, model) if pid and model else None
    if " " in value:
        pid, _, model = value.partition(" ")
        return (pid, model) if pid and model else None
    return None


async def provider_choose(
    ctx: RunContext[AgentDeps],
    action: ProviderAction,
    value: str = "",
) -> str:
    """管理当前会话的 provider / 文本模型 / vision（仅超级用户可用）。

    - status：查看当前 provider、文本模型与 vision、API 可用模型清单
    - provider <id>：把当前会话切换到指定 provider
    - text <model>：设置文本模型（实时校验在 API 可用列表内）
    - vision <provider> <model> 或 vision <provider>/<model>：设置 vision
      （独立 provider + 模型；实时校验，需真正支持看图）
    - vision none：显式禁用 vision
    - reset [text|vision]：清除模型覆盖，回退 provider 默认 / 全局 vision 默认
    """
    if not ctx.deps.permissions.is_superuser:
        return "该工具仅超级用户可用（superuser），当前用户无权限。"
    scope_key = ctx.deps.scope_key or ""
    actor = ctx.deps.permissions.user_id or ""

    if action == "status":
        return await _status_text(ctx, _effective_provider_id(ctx))

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
            return "用法：text <model>（可用模型见 status）。"
        ok, note = await _validate_model(ctx, pid, value)
        if not ok:
            return note
        store.set_scope_text_model(scope_key, value, updated_by=actor)
        return f"已把文本模型设为 `{value}`（覆盖 provider 默认）{note}".rstrip()

    if action == "vision":
        if not value:
            return "用法：vision <provider> <model>（或 vision <provider>/<model>；vision none 禁用）。"
        if value == "none":
            store.set_scope_vision(scope_key, "", provider.VISION_DISABLED, updated_by=actor)
            return "已显式禁用本会话 vision。"
        spec = _parse_vision_spec(value)
        if spec is None:
            return "用法：vision <provider> <model>（或 vision <provider>/<model>）。"
        vpid, vmodel = spec
        if not provider.has_provider(vpid):
            return f"provider `{vpid}` 不存在。"
        ok, note = await _validate_model(ctx, vpid, vmodel)
        if not ok:
            return note
        store.set_scope_vision(scope_key, vpid, vmodel, updated_by=actor)
        return (
            f"已把 vision 设为 `{vpid}` / `{vmodel}`（本会话）{note}；"
            "该模型需真正支持看图，若识别失败请换模型"
        ).rstrip()

    if action == "reset":
        if value and value not in ("text", "vision"):
            return "用法：reset [text|vision]。"
        slot = value or None
        store.clear_scope_model_override(scope_key, slot)
        if slot == "vision":
            return "已清除 vision 配置，回退全局默认。"
        return "已清除模型覆盖，回退 provider 默认。"

    return "未知 action，可用：status / provider / text / vision / reset。"
