"""web/image_view：抓取图片 URL，用 provider 的 vision 模型描述后交还给调用模型。

先 http(s) 抓取字节，再调用 ``vision.describe_images`` 用当前 provider/scope 的
多模态（vision）模型"看"图并产出文字描述，返回给调用方（通常是默认 text 模型），
由它基于描述继续作答——text 模型不必自己具备视觉能力。

网络行为与 web_fetch 一致：``trust_env=False``（规避 socks 环境变量崩溃）、
``verify=config.web_fetch_verify_ssl``、SSRF 防护（拒绝私有/回环/保留地址）、
30s 超时、跟随重定向。超过 10MB 的图片先压缩（PIL thumbnail + JPEG/80）再送
vision，压缩后仍超限才拒绝。无 vision 模型时返回明确提示。
"""

from __future__ import annotations

from io import BytesIO
from urllib.parse import urlparse

import httpx
from pydantic_ai import BinaryContent, RunContext

from ... import vision
from ...deps import AgentDeps
from hoshino.ai.tools.web.net import is_private_host

_MAX_BYTES = 15 * 1024 * 1024  # 抓取上限（压缩前的网络字节）
_COMPRESS_THRESHOLD = 10 * 1024 * 1024  # 超过此大小先压缩
_COMPRESS_MAX = 10 * 1024 * 1024  # 压缩后仍超过则拒绝
_ALLOWED_SCHEMES = ("http", "https")
_IMAGE_MEDIA_TYPES = ("image/png", "image/jpeg", "image/webp", "image/gif")


def _media_type_from_content_type(content_type: str | None) -> str:
    """从响应头推断图片 media_type；未知一律按 image/png 处理。"""
    if content_type:
        ct = content_type.split(";")[0].strip().lower()
        if ct in _IMAGE_MEDIA_TYPES:
            return ct
    return "image/png"


def _compress_image(data: bytes) -> bytes:
    """把图片压缩到 10MB 以下（thumbnail + JPEG/80）；原图已达标则原样返回。"""
    if len(data) <= _COMPRESS_THRESHOLD:
        return data
    try:
        from PIL import Image as PILImage

        image = PILImage.open(BytesIO(data))
        image.thumbnail((4096, 4096))
        if image.mode != "RGB":
            image = image.convert("RGB")
        buffered = BytesIO()
        image.save(buffered, format="JPEG", quality=80)
        return buffered.getvalue()
    except Exception:
        return data  # 压缩失败按原字节继续（超限判定在调用方）


async def describe_image_url(
    url: str,
    *,
    verify_ssl: bool,
    proxy: str | None,
    record,
    vision_model: str,
) -> str:
    """抓取图片 URL 并用 vision 模型描述（供 image_view 工具与 zssm 复用）。

    校验协议/SSRF → httpx 抓取（trust_env=False）→ 超限压缩 → vision 描述。
    失败返回错误提示字符串（供直接展示），成功返回描述文本。
    """
    parsed = urlparse(url)
    if parsed.scheme not in _ALLOWED_SCHEMES or not parsed.hostname:
        return "仅支持 http/https 图片 URL。"
    if is_private_host(parsed.hostname):
        return "拒绝访问私有/内网地址。"

    async with httpx.AsyncClient(
        trust_env=False,
        verify=verify_ssl,
        timeout=httpx.Timeout(30.0),
        follow_redirects=True,
    ) as client:
        try:
            response = await client.get(url)
            response.raise_for_status()
        except (httpx.HTTPError, ValueError) as exc:
            return f"图片抓取失败（{type(exc).__name__}）。"

    data = response.content
    if not data:
        return "图片内容为空。"
    if len(data) > _MAX_BYTES:
        return f"图片超过大小限制（{_MAX_BYTES // (1024 * 1024)}MB）。"
    data = _compress_image(data)
    if len(data) > _COMPRESS_MAX:
        return f"图片压缩后仍超过 {_COMPRESS_MAX // (1024 * 1024)}MB。"

    content = [
        BinaryContent(
            data=data,
            media_type=_media_type_from_content_type(
                response.headers.get("content-type")
            ),
        )
    ]
    try:
        description = await vision.describe_images(
            record, vision_model, content, proxy=proxy
        )
    except Exception as exc:
        return f"图片识别失败（{type(exc).__name__}）。"
    return description or "（图片暂无可识别内容）"


async def image_view(ctx: RunContext[AgentDeps], url: str):
    """抓取指定 URL 的图片，用 vision 模型识别后返回文字描述。

    仅当需要查看具体图片 URL 的内容时使用；禁止访问私有/内网地址。
    当前 provider 未配置 vision 模型时返回提示（无法看图）。
    """
    parsed = urlparse(url)
    if parsed.scheme not in _ALLOWED_SCHEMES or not parsed.hostname:
        return "仅支持 http/https 图片 URL。"
    if is_private_host(parsed.hostname):
        return "拒绝访问私有/内网地址。"

    record, vision_model = vision.resolve_vision_model(ctx)
    if record is None:
        return "provider 配置异常。"
    if not vision_model:
        return "当前 provider 未配置 vision 模型，无法识别图片。"
    return await describe_image_url(
        url,
        verify_ssl=ctx.deps.config.web_fetch_verify_ssl,
        proxy=ctx.deps.config.proxy,
        record=record,
        vision_model=vision_model,
    )


tool = image_view
