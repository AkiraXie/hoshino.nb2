"""zssm 图片处理：事件图片 → image_view 链路（抓取 + vision 描述）。

- 远程 http(s) 图片走 ``image_view.describe_image_url``（SSRF 防护 + 10MB 压缩
  + vision 描述），与 image_view 工具同一实现；
- 本地 path/raw 图片转 BinaryContent 直送 ``vision.describe_images``；
- 描述 prompt 使用"文本模型的眼睛"角色设定（参考 djkcyl zssm）：vision 模型
  知道自己的描述会被另一个模型阅读；
- 描述按图片出现顺序分块（``图片N：…``），与主 prompt 的纠错引导配套；
- 任一图片失败直接抛 ``ValueError``（调用方直接回复错误，不做重试）。
"""

from __future__ import annotations

import asyncio

from loguru import logger
from nonebot.adapters import Bot, Event
from nonebot_plugin_alconna.uniseg import Image as UniImage

from hoshino.ai import media as ai_media
from hoshino.ai import vision
from hoshino.ai.tools.core.image_view import describe_image_url
from hoshino.util.media import get_event_media_segments

# vision 描述的角色设定：文本模型的眼睛（描述会被另一个模型阅读）。
_EYE_PROMPT = (
    "你是文本模型的眼睛。文本模型看不到图片，只能依赖你的描述。"
    "请客观、详细地描述图片中的主体、文字、图表与显著关系，供其解释。"
)

# describe_image_url 的错误提示前缀（据此判定失败）。
_IMAGE_ERROR_PREFIXES = (
    "仅支持",
    "拒绝",
    "图片抓取失败",
    "图片内容为空",
    "图片超过大小限制",
    "图片压缩后仍超过",
    "图片识别失败",
)


async def event_images(bot: Bot, event: Event) -> list:
    """提取事件中的图片段（含回复引用/转发）；解析失败按无图处理。"""
    try:
        return await get_event_media_segments(bot, event, UniImage)
    except Exception as exc:
        logger.warning(f"zssm 媒体段解析失败 error={type(exc).__name__}")
        return []


def _segment_url(segment) -> str:
    return (getattr(segment, "url", "") or "").strip()


def _is_error_text(text: str) -> bool:
    return bool(text) and text.startswith(_IMAGE_ERROR_PREFIXES)


async def _describe_one(
    segment,
    *,
    record,
    vision_model: str,
    config,
) -> str:
    """描述单张图片；失败返回错误提示文本（不抛异常）。"""
    url = _segment_url(segment)
    if url.startswith(("http://", "https://")):
        return await describe_image_url(
            url,
            verify_ssl=config.web_fetch_verify_ssl,
            proxy=config.proxy,
            record=record,
            vision_model=vision_model,
        )
    # 本地 path / raw 字节 / file:// 等：转 BinaryContent 直送 vision
    # （本地文件读取为阻塞 I/O，放线程池执行，避免阻塞事件循环）
    content = await asyncio.to_thread(ai_media.image_segments_to_content, [segment])
    if not content:
        return "图片解析失败（无法读取图片内容）。"
    try:
        description = await vision.describe_images(
            record,
            vision_model,
            content,
            proxy=config.proxy,
            prompt=_EYE_PROMPT,
        )
    except Exception as exc:
        return f"图片识别失败（{type(exc).__name__}）。"
    return description or "（图片暂无可识别内容）"


async def describe_event_images(
    images: list,
    *,
    record,
    vision_model: str,
    config,
) -> str:
    """逐张描述事件图片，返回 ``图片N：…`` 分块文本；任一失败抛 ValueError。

    未配置 vision 模型时抛 ValueError（纯图片场景由调用方直接提示）。
    """
    if not vision_model:
        raise ValueError("当前未配置多模态模型，无法识别图片内容。")
    parts: list[str] = []
    for index, segment in enumerate(images, start=1):
        desc = await _describe_one(segment, record=record, vision_model=vision_model, config=config)
        if _is_error_text(desc):
            raise ValueError(desc)
        parts.append(f"图片{index}：{desc}")
    return "\n".join(parts)
