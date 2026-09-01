"""core/provider_choose：超级用户调整当前 scope 的统一 model。

把 ``ai model set`` / ``ai model reset`` 等管理员命令的语义做成 LLM 工具：
superuser 可以直接让模型帮自己设定 (provider, model)。可用模型一律调用
provider API 实时获取校验（本地不维护 model-list）。

provider 是全局资源，不与 scope 绑定；只写 scope 级模型覆盖
（``ai_scope_models``），不动全局默认。
"""

from __future__ import annotations

from typing import Literal

from pydantic_ai import RunContext

from ... import provider, store
from ...deps import AgentDeps

ProviderAction = Literal["status", "provider", "model", "reset"]


def _effective_provider_id(ctx: RunContext[AgentDeps]) -> str:
    """当前生效的 provider id（仅取全局默认）；无则空串。"""
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
    if pid:
        lines.append(f"provider：`{pid}`（全局默认）")
    model_pid, model = provider.resolve_model(scope_key)
    if model_pid and model:
        lines.append(f"model：`{model_pid}` / `{model}`")
    else:
        lines.append("model：`（未配置，请超级用户 ai model default）`")
    if pid:
        models = await _available_models(ctx, pid)
        if models:
            lines.append(
                "该 provider 可用模型（API 实时获取）：" + "、".join(f"`{m}`" for m in models)
            )
        else:
            lines.append("可用模型获取失败（网络或端点不支持）。")
    elif not model_pid:
        lines.append("没有可用 provider（未设置默认）。")
    return "\n".join(lines)


async def _validate_model(ctx: RunContext[AgentDeps], pid: str, model: str) -> tuple[bool, str]:
    """实时校验模型：返回 (ok, 附加信息)。网络失败放行并附警告。"""
    available = await _available_models(ctx, pid)
    if available is None:
        return True, "（无法连接 provider 校验，已直接设置）"
    if model not in available:
        return False, f"模型 `{model}` 不在该 provider 的 API 可用列表中。"
    return True, ""


def _parse_model_spec(value: str) -> tuple[str, str] | None:
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
    """管理当前会话的统一 model，以及全局默认 provider（仅超级用户可用）。

    - status：查看当前 provider、model、API 可用模型清单
    - provider <id>：切换全局默认 provider（不与 scope 绑定）
    - model <provider> <model> 或 model <provider>/<model>：设置本会话 model
    - reset：清除本会话 model 覆盖，回退全局默认
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
        store.set_global_value("default_provider", value)
        return f"已将全局默认 provider 切换为 `{value}`。"

    if action == "model":
        if not value:
            return "用法：model <provider> <model>（或 model <provider>/<model>）。"
        spec = _parse_model_spec(value)
        if spec is None:
            return "用法：model <provider> <model>（或 model <provider>/<model>）。"
        mpid, mmodel = spec
        if not provider.has_provider(mpid):
            return f"provider `{mpid}` 不存在。"
        ok, note = await _validate_model(ctx, mpid, mmodel)
        if not ok:
            return note
        store.set_scope_model(scope_key, mpid, mmodel, updated_by=actor)
        return f"已把 model 设为 `{mpid}` / `{mmodel}`（本会话）{note}".rstrip()

    if action == "reset":
        if value:
            return "用法：reset（清除本会话 model 覆盖）。"
        cleared = store.clear_scope_model(scope_key)
        if not cleared:
            return "本会话当前没有 model 覆盖。"
        return "已清除 model 覆盖，回退全局默认。"

    return "未知 action，可用：status / provider / model / reset。"
