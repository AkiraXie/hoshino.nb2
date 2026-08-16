"""vision 模型看图：文本描述子请求（vision 描述 → 默认模型作答）。

聊天与 image_view 工具都走这里：当前 provider/scope 配了多模态（vision）模型时，
用 vision 模型"看"图并产出文字描述，再把描述交给默认（text）模型继续作答；
无 vision 模型时返回空串，由调用方降级（如回复"未启用多模态"）。

只做一次直接 ``Model.request`` 子请求（不进入 Agent 图，避免嵌套 Agent.run）；
描述请求不带任何工具，避免副作用。model 实例按 (provider, model, proxy) 缓存，
http client 与 build_model 同源，缓存注册到 ``providers`` 的统一 model 缓存清单，
由 ``clear_agent_cache`` 一并清空并关闭 client。
"""

from __future__ import annotations

from typing import Any

from pydantic_ai.messages import (
    ModelRequest,
    SystemPromptPart,
    TextContent,
    UserPromptPart,
)
from pydantic_ai.models import ModelRequestParameters, ModelSettings

from .provider import ProviderRecord

_DESCRIBE_SYSTEM = (
    "你是图片描述助手。用简洁、客观、准确的中文描述图片内容："
    "主体是什么、关键细节、画面里的文字（如截图请转述关键文本）。"
    "只输出描述本身，不要寒暄、不要提问、不要发表评论。"
)

_vision_model_cache: dict[tuple[Any, ...], Any] = {}


def resolve_vision_model(ctx) -> tuple[ProviderRecord | None, str]:
    """解析当前 scope/provider 的 vision 模型；无配置返回 (record, "")。

    record 为 provider 快照（供 build_model / describe_images），空串表示
    当前 provider/scope 没有可用多模态模型。
    """
    from . import provider  # 函数内导入（vision 是底层模块，避免被工具层反向依赖）

    provider_id = ctx.deps.telemetry.provider_id
    record = provider.get_provider(provider_id)
    if record is None:
        return None, ""
    _, vision_model = provider.resolve_models(ctx.deps.scope_key, provider_id)
    return record, vision_model


def _vision_model(record: ProviderRecord, model: str, *, proxy: str | None) -> Any:
    """构建并缓存 vision 描述用的 model（不包 Agent，只做一次子请求）。"""
    from . import providers  # 函数内导入，避免 providers→tools→image_view→vision 循环

    key = (record.id, record, model, proxy)
    cached = _vision_model_cache.get(key)
    if cached is None:
        cached = providers.build_model(record, model, proxy=proxy)
        _vision_model_cache[key] = cached
        # 缓存与 Agent 共用 build_model 的 http client：注册到统一清单，
        # clear_agent_cache 关闭 client 时一并清空（首次使用时注册，幂等）。
        providers.register_model_cache(_vision_model_cache)
    return cached


async def describe_images(
    record: ProviderRecord,
    vision_model: str,
    image_content: list[Any],
    *,
    proxy: str | None = None,
    prompt: str = "请描述这张图片。",
) -> str:
    """用 vision 模型描述图片，返回文本；失败抛异常（由调用方兜底）。

    ``image_content`` 为 pydantic-ai 的 ImageUrl / BinaryContent 列表
    （``media.image_segments_to_content`` 或 image_view 抓取的 BinaryContent）。
    """
    model = _vision_model(record, vision_model, proxy=proxy)
    request = ModelRequest(
        parts=[
            SystemPromptPart(content=_DESCRIBE_SYSTEM),
            UserPromptPart(content=[*image_content, TextContent(content=prompt)]),
        ]
    )
    response = await model.request([request], ModelSettings(), ModelRequestParameters())
    return response.text or ""
