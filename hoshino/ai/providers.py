"""Pydantic AI model / agent 工厂。

根据 ``ProviderRecord`` + 显式 model 名构建对应协议格式的 model，并按
(provider_id, provider 快照, model, 代理) 缓存 ``Agent``。缓存 key 不含
system_prompt：persona 与工具都通过动态注入解析，不随 scope/绑定变化失效；
一个缓存 Agent 服务多 scope。
"""

from __future__ import annotations

from typing import Any

from loguru import logger
from nonebot_plugin_uninfo import get_session
from pydantic_ai import Agent, RunContext
from pydantic_ai.toolsets import (
    ApprovalRequiredToolset,
    DynamicToolset,
    FunctionToolset,
)

from . import persona, prompts
from .deps import AgentDeps
from .models import (
    build_auxiliary_model,
    build_model,
    build_model_settings,
    clear_model_resources,
    register_model_cache,
)
from .provider import ProviderRecord
from .tools import approval_required, build_tool_instructions, resolve_tools

_agent_cache: dict[tuple[Any, ...], Agent] = {}

# 兼容旧调用方：model 构建 API 仍从本模块 re-export。
__all__ = [
    "build_agent",
    "build_auxiliary_model",
    "build_model",
    "build_model_settings",
    "clear_agent_cache",
    "register_model_cache",
]

OUTPUT_STYLE_HEADER = "\n\n（对了，回复的时候记得按下面的小习惯来：）\n"


async def _persona_system_prompt(ctx: RunContext[AgentDeps]) -> str:
    """每 run 解析 persona：Task 用冻结快照，chat 用三级解析。

    最后统一追加「参考对话风格」（示例对话，锚定说话方式）、实时时间戳（查新/
    时态判断的锚点）与 Markdown 输出规范（``output.md``），使其对所有
    persona / surface 强制生效。
    """
    task = getattr(ctx.deps, "task", None)
    if task is not None:
        base = getattr(task, "persona_prompt", None) or ctx.deps.config.system_prompt
        # Task 是结构化产出（research/plan），不注入示例对话与模板变量。
        dialogs_prompt = ""
    else:
        base = persona.resolve_prompt(ctx.deps.scope_key, ctx.deps.config)
        base = _render_persona_safe(
            base,
            await _persona_variables(ctx),
            scope_key=ctx.deps.scope_key,
        )
        dialogs_prompt = prompts.build_dialogs_prompt(persona.resolve_dialogs(ctx.deps.scope_key))
    time_prompt = f"\n\n{prompts.build_time_prompt()}"
    style = f"{OUTPUT_STYLE_HEADER}{prompts.OUTPUT_STYLE_RULES}"
    if dialogs_prompt:
        return f"{base}\n\n{dialogs_prompt}{time_prompt}{style}"
    return f"{base}{time_prompt}{style}"


async def _persona_variables(ctx: RunContext[AgentDeps]) -> dict[str, str]:
    """构造 persona 模板变量：内置 + 尽力解析群名/发消息人昵称。"""
    variables = persona.builtin_variables(ctx.deps.scope_key)
    event = getattr(ctx.deps, "event", None)
    if event is None:
        return variables
    try:
        session = await get_session(bot=ctx.deps.bot, event=event)
        if session is not None:
            group = getattr(session, "group", None)
            if group is not None and getattr(group, "group_name", None):
                variables["group_name"] = str(group.group_name)
            member = getattr(session, "member", None)
            if member is not None and getattr(member, "user_name", None):
                variables["user_name"] = str(member.user_name)
    except Exception:
        logger.debug("AI 群名/昵称解析失败，保留空串，不阻塞主流程", exc_info=True)
    return variables


def _render_persona_safe(text: str, variables: dict[str, str], *, scope_key) -> str:
    """渲染 persona 模板；未知变量 fail loud 但回退原文并记日志。"""
    try:
        return persona.render_persona(text, variables)
    except ValueError as exc:
        logger.warning(f"AI persona 模板渲染失败 scope={scope_key} error={exc}")
        return text


def _resolve_toolset(ctx: RunContext[AgentDeps]) -> FunctionToolset | None:
    """每 run 按 deps 解析工具集；无工具时返回 None（DynamicToolset 接受 None）。"""
    tools = resolve_tools(ctx.deps)
    if not tools:
        return None
    return FunctionToolset(tools, instructions=build_tool_instructions(ctx.deps))


def build_agent(
    provider_id: str,
    provider: ProviderRecord,
    model: str,
    *,
    proxy: str | None = None,
    tool_max_retries: int = 3,
) -> Agent:
    """构建并缓存 Agent。缓存 key 含 provider 快照、model 名与代理。

    ``tool_max_retries``：工具调用失败重试预算，默认 3（pydantic-ai 默认 1，
    web_fetch 类抓取工具偶发失败会触发 "exceeded max retries" 杀掉整轮 run）。
    联网搜索不在此注入 capability：统一走 ``web_search`` 工具（dsh 同款独立
    原生搜索请求，见 ``tools/web/web_search.py``）。
    """
    key = (provider_id, provider, model, proxy, tool_max_retries)
    agent = _agent_cache.get(key)
    if agent is None:
        model_obj = build_model(provider, model, proxy=proxy)
        model_settings = build_model_settings(provider)
        agent = Agent(
            model=model_obj,
            model_settings=model_settings,
            deps_type=AgentDeps,
            retries={"tools": max(1, tool_max_retries)},
            toolsets=[
                # 常驻挂载：approval_required 按 deps 判定，chat（task=None）从不审批。
                # ApprovalRequiredToolset 是 WrapperToolset，需包装 DynamicToolset。
                ApprovalRequiredToolset(
                    DynamicToolset(_resolve_toolset, per_run_step=False),
                    approval_required_func=approval_required,
                ),
            ],
        )
        agent.system_prompt(dynamic=True)(_persona_system_prompt)
        _agent_cache[key] = agent
    return agent


def clear_agent_cache() -> None:
    """清空 Agent / model 缓存并关闭已创建的 http client（配置变更或测试时使用）。"""
    _agent_cache.clear()
    clear_model_resources()
