"""Pydantic AI model 构建（无 tools/agent 依赖）。

从 ``providers`` 下沉，打破 ``web_fetch → compaction → providers → tools → web_fetch``
循环：摘要/压缩只依赖本模块 + ``provider``，不拉 tools 包。
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from typing import Any

import httpx
from pydantic import ValidationError
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.models.openai import OpenAIChatModel, OpenAIResponsesModel
from pydantic_ai.providers.anthropic import AnthropicProvider
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.settings import ModelSettings

from .provider import ProviderRecord

# build_model 创建的 http client，供 clear_model_resources 关闭，避免泄漏。
_http_clients: list[httpx.AsyncClient] = []
# 子请求 model 缓存（如 zssm / compaction）注册到这里：与 Agent 共用 build_model
# 创建的 http client，client 关闭后必须一并清空。
_model_caches: list[dict] = []
_auxiliary_model_cache: dict[tuple[Any, ...], Any] = {}


def register_model_cache(cache: dict) -> None:
    """注册一个 model 实例缓存；``clear_model_resources`` 时统一清空（幂等）。"""
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
    if record.timeout_seconds is not None:
        settings["timeout"] = record.timeout_seconds
    return ModelSettings(**settings) if settings else None


class _ResponseBodyOpenAIChatModel(OpenAIChatModel):
    """``openai_chat`` 响应容错与失败可观测性：空 function_call 归一化 + 原始响应体随异常。

    两个职责：
    1. **空 legacy function_call 容错**：opencode-go 等 OpenAI 兼容网关在每条响应里
       附加 ``function_call: {name: null, arguments: null}`` 空占位（无论是否真的
       调用工具），pydantic-ai 严格校验必填 ``str`` 字段会拒绝整个响应。该字段为
       null 表示模型没有 legacy function_call，校验前置 None 即可；工具调用走
       ``tool_calls`` 字段，pydantic-ai ``_process_response`` 不读 function_call。
    2. **原始响应体随异常**：校验失败（非空占位类畸形）时把 ``response.model_dump()``
       序列化进异常 ``body``（pydantic-ai 默认 body=None），``errors.format_exception_detail``
       现有的 ``body=`` 提取 + 截断逻辑自动生效，chat/task 失败日志可看到原始 JSON。
    """

    def _validate_completion(self, response: Any) -> Any:
        _drop_empty_function_call(response)
        try:
            return super()._validate_completion(response)
        except ValidationError as exc:
            raw = json.dumps(response.model_dump(), ensure_ascii=False, default=str)
            raise UnexpectedModelBehavior(
                f"Invalid response from {self.system} chat completions endpoint: {exc}",
                body=raw,
            ) from exc


def _attr_or_item(obj: Any, key: str) -> Any:
    """dict / pydantic 对象统一的字段读取。"""
    if isinstance(obj, dict):
        return obj.get(key)
    return getattr(obj, key, None)


def _drop_empty_function_call(response: Any) -> None:
    """把网关返回的空 legacy function_call 占位移除（name/arguments 均为空）。"""
    for choice in _attr_or_item(response, "choices") or []:
        message = _attr_or_item(choice, "message")
        if message is None:
            continue
        fc = _attr_or_item(message, "function_call")
        if fc is None:
            continue
        name = _attr_or_item(fc, "name")
        arguments = _attr_or_item(fc, "arguments")
        if not name and not arguments:
            if isinstance(message, dict):
                message["function_call"] = None
            else:
                message.function_call = None


def build_model(provider: ProviderRecord, model: str, *, proxy: str | None = None) -> Any:
    """按 provider.kind 与显式 model 名构建 pydantic-ai model。"""
    if not model:
        raise ValueError("provider 未配置 model")
    url = provider.url or None
    http_client = _build_http_client(proxy)
    match provider.kind:
        case "openai_chat":
            return _ResponseBodyOpenAIChatModel(
                model,
                provider=OpenAIProvider(
                    api_key=provider.key, base_url=url, http_client=http_client
                ),
            )
        case "openai_responses":
            return OpenAIResponsesModel(
                model,
                provider=OpenAIProvider(
                    api_key=provider.key, base_url=url, http_client=http_client
                ),
            )
        case "anthropic":
            return AnthropicModel(
                model,
                provider=AnthropicProvider(
                    api_key=provider.key, base_url=url, http_client=http_client
                ),
            )
        case _:
            raise ValueError(f"未知 provider kind: {provider.kind}")


def build_auxiliary_model(provider: ProviderRecord, model: str, *, proxy: str | None = None) -> Any:
    """构建并缓存摘要等短辅助请求使用的 model。"""
    key = (provider, model, proxy)
    cached = _auxiliary_model_cache.get(key)
    if cached is None:
        cached = build_model(provider, model, proxy=proxy)
        _auxiliary_model_cache[key] = cached
        register_model_cache(_auxiliary_model_cache)
    return cached


def clear_model_resources() -> None:
    """清空 model 缓存并关闭已创建的 http client。"""
    for cache in _model_caches:
        cache.clear()
    clients, _http_clients[:] = _http_clients, []
    for client in clients:
        with contextlib.suppress(RuntimeError):
            asyncio.get_running_loop().create_task(client.aclose())
