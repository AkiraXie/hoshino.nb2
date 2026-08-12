"""Pydantic AI model / agent 工厂。

根据 ``ProviderConfig`` 构建对应协议格式的 model，并按 (provider_id, 配置,
system_prompt) 缓存 ``Agent``。provider 配置更新后，缓存 key 自然变化，
旧 Agent 实例被 GC，无需手动失效。
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
from pydantic_ai import Agent
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.models.openai import OpenAIChatModel, OpenAIResponsesModel
from pydantic_ai.providers.anthropic import AnthropicProvider
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.settings import ModelSettings

from .config import ProviderConfig, ProviderOptions

_agent_cache: dict[tuple[Any, ...], Agent] = {}
# build_model 创建的 http client，供 clear_agent_cache 关闭，避免泄漏。
_http_clients: list[httpx.AsyncClient] = []


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


def build_model_settings(opts: ProviderOptions) -> ModelSettings | None:
    """把非 None 的采样参数转成 ModelSettings（TypedDict）。"""
    settings: dict[str, Any] = {}
    if opts.temperature is not None:
        settings["temperature"] = opts.temperature
    if opts.max_tokens is not None:
        settings["max_tokens"] = opts.max_tokens
    if opts.timeout_seconds is not None:
        settings["timeout"] = opts.timeout_seconds
    return ModelSettings(**settings) if settings else None


def build_model(provider_config: ProviderConfig, *, proxy: str | None = None) -> Any:
    """根据 ProviderConfig 构建 pydantic-ai model。"""
    opts = provider_config.config
    url = provider_config.url or None
    if not opts.model:
        raise ValueError("provider 未配置 model")
    http_client = _build_http_client(proxy)
    if opts.kind == "openai_chat":
        return OpenAIChatModel(
            opts.model,
            provider=OpenAIProvider(
                api_key=provider_config.key, base_url=url, http_client=http_client
            ),
        )
    if opts.kind == "openai_responses":
        return OpenAIResponsesModel(
            opts.model,
            provider=OpenAIProvider(
                api_key=provider_config.key, base_url=url, http_client=http_client
            ),
        )
    if opts.kind == "anthropic":
        return AnthropicModel(
            opts.model,
            provider=AnthropicProvider(
                api_key=provider_config.key, base_url=url, http_client=http_client
            ),
        )
    raise ValueError(f"未知 provider kind: {opts.kind}")


def build_agent(
    provider_id: str,
    provider_config: ProviderConfig,
    system_prompt: str,
    *,
    proxy: str | None = None,
) -> Agent:
    """构建并缓存 Agent。缓存 key 含 provider 配置、system_prompt 与代理。"""
    key = (provider_id, provider_config, system_prompt, proxy)
    agent = _agent_cache.get(key)
    if agent is None:
        model = build_model(provider_config, proxy=proxy)
        model_settings = build_model_settings(provider_config.config)
        agent = Agent(
            model=model,
            system_prompt=system_prompt,
            model_settings=model_settings,
        )
        _agent_cache[key] = agent
    return agent


def clear_agent_cache() -> None:
    """清空 Agent 缓存并关闭已创建的 http client（配置变更或测试时使用）。"""
    _agent_cache.clear()
    clients, _http_clients[:] = _http_clients, []
    for client in clients:
        try:
            asyncio.get_running_loop().create_task(client.aclose())
        except RuntimeError:
            pass  # 无事件循环（脚本/部分测试），交由 GC 处理
