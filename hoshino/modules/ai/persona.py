"""persona 解析接口。

首期固定返回全局 ``AIConfig.system_prompt``，与 provider/scope 配置解耦；
后续可扩展为 scope/conversation/provider 多级 persona 覆盖。
"""

from __future__ import annotations

from .config import AIConfig


def resolve_persona(scope_key: str | None, config: AIConfig) -> str:
    """返回本次调用使用的 system_prompt。首期与 scope 无关。"""
    return config.system_prompt
