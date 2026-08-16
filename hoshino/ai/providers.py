"""Pydantic AI model / agent 工厂。

根据 ``ProviderRecord`` + 显式 model 名构建对应协议格式的 model，并按
(provider_id, provider 快照, model, 代理) 缓存 ``Agent``。缓存 key 不含
system_prompt：persona 与工具都通过动态注入解析，不随 scope/绑定变化失效；
一个缓存 Agent 服务多 scope。
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from typing import Any

import httpx
from loguru import logger
from pydantic import ValidationError
from pydantic_ai import Agent, RunContext
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.models.openai import OpenAIChatModel, OpenAIResponsesModel
from pydantic_ai.providers.anthropic import AnthropicProvider
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.settings import ModelSettings
from pydantic_ai.toolsets import (
    ApprovalRequiredToolset,
    DynamicToolset,
    FunctionToolset,
)

from . import persona, prompts
from .deps import AgentDeps
from .provider import ProviderRecord
from .tools import approval_required, build_tool_instructions, resolve_tools

_agent_cache: dict[tuple[Any, ...], Agent] = {}
# build_model 创建的 http client，供 clear_agent_cache 关闭，避免泄漏。
_http_clients: list[httpx.AsyncClient] = []
# 子请求 model 缓存（vision / zssm）注册到这里：它们与 Agent 共用 build_model
# 创建的 http client，clear_agent_cache 关闭 client 后必须一并清空，否则缓存仍
# 指向已关闭的 client，provider 变更后看图 / zssm 请求失败直至重启。
_model_caches: list[dict] = []


def register_model_cache(cache: dict) -> None:
    """注册一个 model 实例缓存；``clear_agent_cache`` 时统一清空（幂等）。"""
    if cache not in _model_caches:
        _model_caches.append(cache)


def _httpx_proxy(proxy: str | None) -> str | None:
    """把 socks:// 归一化为 socks5://，与 info-x 的约定一致。"""
    if proxy and proxy.startswith("socks://"):
        return f"socks5://{proxy.removeprefix('socks://')}"
    return proxy


def _build_http_client(proxy: str | None) -> httpx.AsyncClient:
    """构建 provider 使用的 http client。

    用 ``trust_env=False`` 显式忽略环境变量代理——否则 ``ALL_PROXY=socks://...``
    这类无法被 httpx 解析的值会在构造 client 时直接抛异常，导致 AI 请求不可用。
    """
    client = httpx.AsyncClient(
        proxy=_httpx_proxy(proxy),
        trust_env=False,
        timeout=httpx.Timeout(60.0),
    )
    _http_clients.append(client)
    return client


def build_model_settings(record: ProviderRecord) -> ModelSettings | None:
    """把 provider 行的非 None 采样参数转成 ModelSettings（TypedDict）。"""
    settings: dict[str, Any] = {}
    if record.temperature is not None:
        settings["temperature"] = record.temperature
    if record.max_tokens is not None:
        settings["max_tokens"] = record.max_tokens
    if record.timeout_seconds is not None:
        settings["timeout"] = record.timeout_seconds
    return ModelSettings(**settings) if settings else None


class _ResponseBodyOpenAIChatModel(OpenAIChatModel):
    """``openai_chat`` 响应校验失败时把原始响应体附到异常，供失败日志定位。

    pydantic-ai 的 ``_process_response`` 在 ``_validate_completion`` 校验失败时抛
    ``UnexpectedModelBehavior`` 但不带 ``body``（body=None）。上游网关（如
    opencode-go）返回 ``function_call`` 的 name/arguments 为 null 的畸形响应时，
    日志只能看到 pydantic 校验错误文本，看不到原始 JSON，无法判断是模型幻觉还是
    网关转译问题。此处覆盖公开 hook（openrouter.py 同款扩展点），校验失败时把
    ``response.model_dump()`` 序列化进异常 ``body``；``errors.format_exception_detail``
    现有的 ``body=`` 提取 + 截断逻辑自动生效，chat/task 失败日志无需改动。
    """

    def _validate_completion(self, response: Any) -> Any:
        try:
            return super()._validate_completion(response)
        except ValidationError as exc:
            raw = json.dumps(response.model_dump(), ensure_ascii=False, default=str)
            raise UnexpectedModelBehavior(
                f"Invalid response from {self.system} chat completions endpoint: {exc}",
                body=raw,
            ) from exc


def build_model(provider: ProviderRecord, model: str, *, proxy: str | None = None) -> Any:
    """按 provider.kind 与显式 model 名构建 pydantic-ai model。"""
    if not model:
        raise ValueError("provider 未配置 model")
    url = provider.url or None
    http_client = _build_http_client(proxy)
    if provider.kind == "openai_chat":
        return _ResponseBodyOpenAIChatModel(
            model,
            provider=OpenAIProvider(api_key=provider.key, base_url=url, http_client=http_client),
        )
    if provider.kind == "openai_responses":
        return OpenAIResponsesModel(
            model,
            provider=OpenAIProvider(api_key=provider.key, base_url=url, http_client=http_client),
        )
    if provider.kind == "anthropic":
        return AnthropicModel(
            model,
            provider=AnthropicProvider(api_key=provider.key, base_url=url, http_client=http_client),
        )
    raise ValueError(f"未知 provider kind: {provider.kind}")


OUTPUT_STYLE_HEADER = "\n\n（对了，回复的时候记得按下面的小习惯来：）\n"


async def _persona_system_prompt(ctx: RunContext[AgentDeps]) -> str:
    """每 run 解析 persona：Task 用冻结快照，chat 用三级解析。

    最后统一追加「参考对话风格」（示例对话，锚定说话方式）与 Markdown 输出规范
    （``output.md``），使其对所有 persona / surface 强制生效。
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
    style = f"{OUTPUT_STYLE_HEADER}{prompts.OUTPUT_STYLE_RULES}"
    if dialogs_prompt:
        return f"{base}\n\n{dialogs_prompt}{style}"
    return f"{base}{style}"


async def _persona_variables(ctx: RunContext[AgentDeps]) -> dict[str, str]:
    """构造 persona 模板变量：内置 + 尽力解析群名/发消息人昵称。"""
    variables = persona.builtin_variables(ctx.deps.scope_key)
    event = getattr(ctx.deps, "event", None)
    if event is None:
        return variables
    try:
        from nonebot_plugin_uninfo import get_session

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


def _build_web_search_capability(provider: ProviderRecord) -> Any | None:
    """按 provider kind 决定是否注入原生联网搜索能力。

    pydantic-ai 的 ``WebSearch`` 原生工具只在支持服务端 web_search 的模型上可用：
    anthropic（含 DeepSeek ``/anthropic`` 端点，服务端 ``web_search_20250305`` 工具）
    与 openai_responses。openai_chat 会直接抛 ``UserError``，故返回 None，由既有的
    duckduckgo_search / web_fetch 工具承担搜索。
    """
    if provider.kind not in ("anthropic", "openai_responses"):
        return None
    # 函数内导入：只在需要时拉取 capability 机制（openai_chat 等 kind 不加载）。
    from pydantic_ai.capabilities import WebSearch

    return WebSearch(local=False)


def build_agent(
    provider_id: str,
    provider: ProviderRecord,
    model: str,
    *,
    proxy: str | None = None,
    web_search_native: bool = True,
    tool_max_retries: int = 3,
) -> Agent:
    """构建并缓存 Agent。缓存 key 含 provider 快照、model 名与代理。

    ``web_search_native``：注入服务端原生 web_search 能力（kind 不支持时自动跳过）；
    ``tool_max_retries``：工具调用失败重试预算，默认 3（pydantic-ai 默认 1，
    web_fetch 类抓取工具偶发失败会触发 "exceeded max retries" 杀掉整轮 run）。
    """
    key = (provider_id, provider, model, proxy, web_search_native, tool_max_retries)
    agent = _agent_cache.get(key)
    if agent is None:
        model_obj = build_model(provider, model, proxy=proxy)
        model_settings = build_model_settings(provider)
        capabilities: list[Any] = []
        if web_search_native:
            capability = _build_web_search_capability(provider)
            if capability is not None:
                capabilities.append(capability)
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
            capabilities=capabilities,
        )
        agent.system_prompt(dynamic=True)(_persona_system_prompt)
        _agent_cache[key] = agent
    return agent


def clear_agent_cache() -> None:
    """清空 Agent / model 缓存并关闭已创建的 http client（配置变更或测试时使用）。

    ``_model_caches`` 覆盖 vision / zssm 等子请求 model 缓存：它们与 Agent 共用
    build_model 的 http client，client 关闭后必须同步失效，否则后续请求
    “Cannot send a request, as the client has been closed” 直到重启。
    """
    _agent_cache.clear()
    for cache in _model_caches:
        cache.clear()
    clients, _http_clients[:] = _http_clients, []
    for client in clients:
        # 无事件循环（脚本/部分测试）时忽略，交由 GC 处理。
        with contextlib.suppress(RuntimeError):
            asyncio.get_running_loop().create_task(client.aclose())
