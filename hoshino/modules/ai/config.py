"""AI 模块配置数据模型。

配置由 ``hoshino/core/service.py`` 的 ``Service(config_type=AIConfig)`` 管理，
首次加载自动生成 ``hoshino/service_config/aichat.json``。
provider 的 key 明文落 JSON（用户明确要求），写入 ``hoshino/service_config/``
该目录已被 .gitignore 忽略；任何日志、命令输出都必须脱敏。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

ProviderKind = Literal["openai_chat", "openai_responses", "anthropic"]
ThemeKind = Literal["light", "dark"]


@dataclass(frozen=True, slots=True)
class ProviderOptions:
    """单个 provider 的采样参数。None 表示沿用模型/网关默认值。"""

    kind: ProviderKind = "openai_chat"
    model: str = ""
    temperature: float | None = None
    max_tokens: int | None = None
    timeout_seconds: float | None = None


@dataclass(frozen=True, slots=True)
class ProviderConfig:
    """一个 provider 的接入配置。key/url 都是配置项，明文落 JSON。"""

    url: str = ""
    key: str = ""
    config: ProviderOptions = field(default_factory=ProviderOptions)


@dataclass(frozen=True, slots=True)
class AIConfig:
    default: str = ""
    system_prompt: str = "你是 HoshinoBot 的群聊助手，回答简洁、准确。"
    max_history_messages: int = 40
    render_timeout_seconds: float = 30.0
    render_theme: ThemeKind = "light"
    # 代理走显式配置而非环境变量：与 info-x 一致，避免读入无法解析的
    # ``ALL_PROXY=socks://...`` 环境变量导致 httpx 崩溃。支持 http(s):// 与
    # socks://（后者归一化为 socks5://）。
    proxy: str | None = None
    providers: dict[str, ProviderConfig] = field(default_factory=dict)

    def get_provider(self, provider_id: str) -> ProviderConfig | None:
        return self.providers.get(provider_id)

    def has_provider(self, provider_id: str) -> bool:
        return provider_id in self.providers


def mask_key(key: str) -> str:
    """脱敏 key：只保留前 4 位与后 4 位，中间以星号代替。"""
    if not key:
        return ""
    if len(key) <= 8:
        return "*" * len(key)
    return f"{key[:4]}...{key[-4:]}"


def mask_url(url: str) -> str:
    """脱敏 url：去掉 query/参数中可能的敏感信息，仅保留 scheme+host+path。"""
    if not url:
        return ""
    cleaned = url.split("?")[0].split("#")[0]
    if len(cleaned) <= 48:
        return cleaned
    return f"{cleaned[:44]}...{cleaned[-4:]}"
