"""AI 模块公共入口：配置读取、provider/scope 解析。

Service 不再在此定义：``aichat``（chat.py）与 ``ai_admin``（ai_admin.py，
含 ai task 命令）各自持有。配置由 ``hoshino/ai/config.py`` 的挂载机制注入
``HoshinoConfig``（.env.prod），运行时默认 provider 可被 DB 覆盖
（``ai provider default``）。本模块不 ``import nonebot``，不作为插件加载。
"""

from __future__ import annotations

from . import store
from .config import AIConfig


def get_config() -> AIConfig:
    """读取 AI 配置：``HoshinoConfig.ai``（AI_* env，见 config.py 挂载机制）。

    ``default`` 优先取运行时 DB 覆盖（``ai provider default`` 写入），
    其次取 env 的 ``AI_DEFAULT_PROVIDER``。
    """
    from dataclasses import replace

    from hoshino.core.config import config as hsn

    base = hsn.ai
    default = store.get_global_value("default_provider") or base.default
    return base if default == base.default else replace(base, default=default)


def resolve_provider(scope_key: str | None, config: AIConfig) -> str | None:
    """解析当前 scope 应使用的 provider id。

    优先级：
    1. scope 绑定的 provider（存在且 DB 中有效）。scope_key 为 None 时跳过。
    2. ``AIConfig.default`` 默认 provider（存在且 DB 中有效）。
    3. 两者都缺失时返回 None，由调用方回复配置错误，不发起请求。
    """
    if scope_key:
        bound = store.get_scope_provider(scope_key)
        if bound and store.has_provider_row(bound):
            return bound
    if config.default and store.has_provider_row(config.default):
        return config.default
    return None


def provider_error_message(config: AIConfig) -> str:
    """未配置可用 provider 时的错误提示（用于聊天回复）。"""
    if not store.list_provider_rows():
        return "AI 服务未配置任何 provider，请联系超级用户执行 `ai setup`。"
    if config.default and store.has_provider_row(config.default):
        return "当前会话未绑定 provider 且默认 provider 无效，请联系管理员。"
    return "当前会话未绑定 provider，也没有全局默认 provider，请联系管理员。"
