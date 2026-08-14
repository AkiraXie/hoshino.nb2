"""AI 模块公共入口：共享 Service、配置读取、provider/scope 解析、JSON→DB 迁移。

``chat.py`` / ``ai_admin.py`` / ``task_commands.py`` 复用这里的 ``sv``，保证 service
开关与配置一致。本模块不 ``import nonebot``，不作为插件加载。
"""

from __future__ import annotations

import json
import os

from hoshino.core.hooks import on_serial_startup
from hoshino.core.service import Service

from . import store
from .config import AIConfig

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
        return "AI 服务未配置任何 provider，请联系管理员执行 `ai provider add`。"
    if config.default and store.has_provider_row(config.default):
        return "当前会话未绑定 provider 且默认 provider 无效，请联系管理员。"
    return "当前会话未绑定 provider，也没有全局默认 provider，请联系管理员。"


# ------------------------------------------------------------ JSON → DB 迁移
#
# 旧版把 provider 存在 ``hoshino/service_config/aichat.json`` 的 ``providers`` 字段；
# 启动时一次性迁入 DB（缺 id 才插入，不覆盖 DB 已有数据），随后清空 JSON 字段，
# 避免双源。直接读写 raw JSON（不经过 AIConfig），保证 AIConfig 移除 providers 字段
# 后迁移逻辑仍然成立。


def _service_config_file() -> str:
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "service_config",
        "aichat.json",
    )


def migrate_json_providers(config_path: str | None = None) -> int:
    """把 aichat.json 遗留的 providers 迁入 DB；返回新迁移条数（幂等）。

    ``config_path`` 供测试注入临时文件；为 None 时读真实 service_config。
    """
    path = config_path or _service_config_file()
    try:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, ValueError):
        return 0
    providers = raw.get("providers") or {}
    if not providers:
        return 0

    migrated = 0
    for pid, data in providers.items():
        if store.has_provider_row(pid):
            continue
        opts = data.get("config") or {}
        store.upsert_provider_row(
            provider_id=pid,
            url=data.get("url", ""),
            key=data.get("key", ""),
            kind=opts.get("kind", "openai_chat"),
            default_text_model=opts.get("model", ""),
            default_vision_model="",
            temperature=opts.get("temperature"),
            max_tokens=opts.get("max_tokens"),
            timeout_seconds=opts.get("timeout_seconds"),
        )
        if opts.get("model"):
            store.upsert_provider_model(pid, opts["model"], "text")
        migrated += 1

    if providers:
        raw["providers"] = {}
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(raw, f, ensure_ascii=False, indent=2)
        except OSError:
            sv.logger.warning("AI provider 迁移：写回 aichat.json 失败（DB 已迁移）")
    return migrated


@on_serial_startup
async def _migrate_json_providers() -> None:
    """启动时迁移 JSON providers → DB（在 ensure_schema 之后执行）。"""
    count = migrate_json_providers()
    if count:
        sv.logger.info(f"AI provider 已从 aichat.json 迁移到 DB：{count} 个")
