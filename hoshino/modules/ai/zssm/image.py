"""zssm 图片处理：事件图片 → 压缩后的 BinaryContent（原生多模态）。

远程 http(s) 与本地 path/raw 统一走 ``media.image_segments_to_content_async``
（SSRF 防护 + 压缩），返回 BinaryContent 列表供主流程拼进同一请求。
"""

from __future__ import annotations

from loguru import logger
from nonebot.adapters import Bot, Event
from nonebot_plugin_alconna.uniseg import Image as UniImage

from hoshino.ai import media as ai_media
from hoshino.ai import provider
from hoshino.util.media import get_event_media_segments


async def event_images(bot: Bot, event: Event) -> list:
    """提取事件中的图片段（含回复引用/转发）；解析失败按无图处理。"""
    try:
        return await get_event_media_segments(bot, event, UniImage)
    except Exception as exc:
        logger.warning(f"zssm 媒体段解析失败 error={type(exc).__name__}")
        return []


async def event_image_parts(images: list, *, config) -> list:
    """事件图片 → 压缩 BinaryContent 列表（跳过失败段）。"""
    if not images:
        return []
    return await ai_media.image_segments_to_content_async(
        images,
        verify_ssl=config.web_fetch_verify_ssl,
        proxy=provider.resolve_tool_proxy(config.proxy, tool_use_proxy=config.tool_use_proxy),
    )
