"""AI 运行时目录（唯一事实源）。

附件目录、工具输出溢出目录与 computer 工作根都被多处复用（附件读取白名单、
溢出落盘、提示文案），路径解析集中在此，避免各处各写一份而失配——曾经的
``data/ai_tool_overflow`` 就不在 ``file_view`` 的白名单里，模型被提示去读却读不到。
"""

from __future__ import annotations

import os
from pathlib import Path

from hoshino import data_dir


def attachments_dir() -> Path:
    """收到的聊天附件落盘目录（``file_view`` 白名单根之一）。"""
    return data_dir / "ai_attachments"


def tool_overflow_dir(config) -> Path:
    """工具返回超限时的溢出落盘目录（``file_view`` 白名单根之一）。

    ``config.tool_result_spill_dir`` 非空时覆盖默认的 ``data/ai_tool_overflow``。
    """
    configured = (getattr(config, "tool_result_spill_dir", "") or "").strip()
    if configured:
        return Path(os.path.abspath(os.path.expanduser(configured)))
    return data_dir / "ai_tool_overflow"


__all__ = ["attachments_dir", "tool_overflow_dir"]
