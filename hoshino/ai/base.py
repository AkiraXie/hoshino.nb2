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
    """解析当前应使用的 provider id。

    provider 是全局资源，不与 scope 绑定；仅取 ``AIConfig.default``
    （可被 DB ``default_provider`` 覆盖）。scope_key 参数保留以兼容调用方签名，
    但不再参与解析。
    """
    if config.default and store.has_provider_row(config.default):
        return config.default
    return None


def provider_error_message(config: AIConfig) -> str:
    """未配置可用 provider 时的错误提示（用于聊天回复）。"""
    if not store.list_provider_rows():
        return "AI 服务未配置任何 provider，请联系超级用户执行 `ai setup`。"
    if config.default and store.has_provider_row(config.default):
        return "默认 provider 无效，请联系管理员检查配置。"
    return "未设置默认 provider，请联系管理员执行 `ai setup`。"
