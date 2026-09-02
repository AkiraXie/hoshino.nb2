"""Milky-native file extraction kept outside the generic UniSeg builder."""

from __future__ import annotations

from nonebot_plugin_alconna.uniseg import File as UniFile

from hoshino.platform.milky.bot import get_file_url


async def file_segments(message, *, bot, event) -> list[UniFile]:
    """Convert Milky ``file`` segments, which UniSeg currently drops."""
    result: list[UniFile] = []
    for segment in message or []:
        if getattr(segment, "type", None) != "file":
            continue
        data = getattr(segment, "data", {})
        file_id = data.get("file_id")
        if not file_id:
            continue
        try:
            url = await get_file_url(bot, event, segment)
        except Exception:
            url = None
        result.append(
            UniFile(
                id=str(file_id),
                url=url,
                name=str(data.get("file_name") or "file.bin"),
            )
        )
    return result
