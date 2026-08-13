"""AI 模块公共入口：共享 Service、配置读取、provider/scope 解析。

``chat.py`` 与 ``ai_admin.py`` 复用这里的 ``sv``，保证 service 开关与配置一致。
本模块不 ``import nonebot``，不作为插件加载。
"""

from __future__ import annotations

from hoshino.core.service import Service

from .config import AIConfig
from .store import get_scope_provider

# 唯一共享 Service。首次加载自动生成 hoshino/service_config/aichat.json。
sv = Service(
    "aichat",
    config_type=AIConfig,
    enable_on_default=False,
    visible=False,
)


def get_config() -> AIConfig:
    """读取当前 aichat 服务配置。"""
    return sv.get_config()


def resolve_provider(scope_key: str | None, config: AIConfig) -> str | None:
    """解析当前 scope 应使用的 provider id。

    优先级：
    1. scope 绑定的 provider（存在且配置中有效）。scope_key 为 None 时跳过。
    2. ``AIConfig.default`` 默认 provider（存在且配置中有效）。
    3. 两者都缺失时返回 None，由调用方回复配置错误，不发起请求。
    """
    if scope_key:
        bound = get_scope_provider(scope_key)
        if bound and config.has_provider(bound):
            return bound
    if config.default and config.has_provider(config.default):
        return config.default
    return None


def provider_error_message(config: AIConfig) -> str:
    """未配置可用 provider 时的错误提示（用于聊天回复）。"""
    if not config.providers:
        return "AI 服务未配置任何 provider，请联系管理员执行 `ai provider add`。"
    if config.default and config.has_provider(config.default):
        return "当前会话未绑定 provider 且默认 provider 无效，请联系管理员。"
    return "当前会话未绑定 provider，也没有全局默认 provider，请联系管理员。"
