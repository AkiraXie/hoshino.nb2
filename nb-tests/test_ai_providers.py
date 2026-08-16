"""AI provider DB 层测试：三张新表 CRUD 与 aichat.json → DB 迁移。

store 层测试不启动 NoneBot；``tmp_store`` 把 store.engine/Session 指向临时 SQLite。
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _tmp_store(tmp_store):
    return tmp_store


# ------------------------------------------------------------ provider rows


def test_provider_row_upsert_and_get(tmp_store):
    tmp_store.upsert_provider_row(
        provider_id="deepseek",
        url="https://api.deepseek.com/anthropic",
        key="sk-test",
        kind="anthropic",
        default_text_model="deepseek-v4-flash",
    )
    row = tmp_store.get_provider_row("deepseek")
    assert row["kind"] == "anthropic"
    assert row["default_text_model"] == "deepseek-v4-flash"
    assert row["default_vision_model"] == ""
    assert tmp_store.has_provider_row("deepseek")
    assert not tmp_store.has_provider_row("ghost")


def test_provider_row_upsert_updates_existing(tmp_store):
    tmp_store.upsert_provider_row(provider_id="p", default_text_model="a")
    tmp_store.upsert_provider_row(provider_id="p", default_text_model="b", kind="openai_responses")
    row = tmp_store.get_provider_row("p")
    assert row["default_text_model"] == "b"
    assert row["kind"] == "openai_responses"


def test_provider_row_delete_removes_models(tmp_store):
    tmp_store.upsert_provider_row(provider_id="p", default_text_model="m")
    tmp_store.upsert_provider_model("p", "m", "text")
    assert tmp_store.delete_provider_row("p") is True
    assert not tmp_store.has_provider_row("p")
    assert tmp_store.list_provider_models("p") == []
    assert tmp_store.delete_provider_row("p") is False


# ------------------------------------------------------------ model-list


def test_provider_models_crud(tmp_store):
    tmp_store.upsert_provider_model("p", "text-model", "text")
    tmp_store.upsert_provider_model("p", "vision-model", "multimodal")
    tmp_store.upsert_provider_model("p", "both-model", "both")
    models = tmp_store.list_provider_models("p")
    assert {m["model"] for m in models} == {"text-model", "vision-model", "both-model"}
    by_name = {m["model"]: m["capabilities"] for m in models}
    assert by_name["vision-model"] == "multimodal"
    assert tmp_store.get_provider_model("p", "text-model")["capabilities"] == "text"
    assert tmp_store.delete_provider_model("p", "text-model") is True
    assert tmp_store.get_provider_model("p", "text-model") is None
    assert tmp_store.delete_provider_model("p", "text-model") is False


# ------------------------------------------------------------ scope models


def test_resolve_models_inherit_and_override(tmp_store):
    """双模型解析：scope 覆盖 > provider 默认；none 显式禁用 vision。"""
    from hoshino.ai import provider as provider_domain

    tmp_store.upsert_provider_row(
        provider_id="p",
        kind="openai_chat",
        default_text_model="text-default",
        default_vision_model="vision-default",
    )
    # 无覆盖 → 继承 provider 默认
    assert provider_domain.resolve_models("scope:1", "p") == (
        "text-default",
        "vision-default",
    )
    # scope 覆盖 text，vision 继承
    tmp_store.set_scope_model_override("scope:1", "text", "text-override")
    assert provider_domain.resolve_models("scope:1", "p")[0] == "text-override"
    assert provider_domain.resolve_models("scope:1", "p")[1] == "vision-default"
    # none 显式禁用 vision（provider 默认非空也被关掉）
    tmp_store.set_scope_model_override("scope:1", "vision", "none")
    assert provider_domain.resolve_models("scope:1", "p")[1] == ""
    # provider 不存在 → 双空
    assert provider_domain.resolve_models("scope:1", "ghost") == ("", "")


def test_resolve_text_model_uses_scope_override(tmp_store):
    from hoshino.ai import provider as provider_domain

    tmp_store.upsert_provider_row(provider_id="p", kind="openai_chat", default_text_model="default")
    assert provider_domain.resolve_text_model("scope:1", "p") == "default"
    tmp_store.set_scope_model_override("scope:1", "text", "override")
    assert provider_domain.resolve_text_model("scope:1", "p") == "override"


def test_fetch_available_models_openai(fake_ai_server):
    """fetch_available_models：GET {url}/models + Bearer 鉴权，返回排序后的 id 列表。"""
    import asyncio

    from hoshino.ai.provider import ProviderRecord, fetch_available_models

    base_url, requests = fake_ai_server
    record = ProviderRecord(id="openai", url=base_url, key="sk-test", kind="openai_chat")
    models = asyncio.run(fetch_available_models(record, verify=False))
    assert models == ["gpt-4o", "gpt-4o-mini"]  # 排序
    assert requests[0]["stem"] == "/models"
    assert requests[0]["headers"]["authorization"] == "Bearer sk-test"


def test_fetch_available_models_failure_returns_none():
    """端点不可达/无 key → 返回 None（调用方给提示，不抛异常）。"""
    import asyncio

    from hoshino.ai.provider import ProviderRecord, fetch_available_models

    record = ProviderRecord(id="x", url="http://127.0.0.1:1", key="k", kind="openai_chat")
    assert asyncio.run(fetch_available_models(record, verify=False)) is None
    assert (
        asyncio.run(
            fetch_available_models(
                ProviderRecord(id="x", url="http://127.0.0.1:1", key="", kind="openai_chat"),
                verify=False,
            )
        )
        is None
    )


def test_scope_model_overrides_default_empty(tmp_store):
    assert tmp_store.get_scope_model_overrides("scope:1") == {
        "text_model": "",
        "vision_model": "",
    }


def test_scope_model_override_set_and_clear(tmp_store):
    tmp_store.set_scope_model_override("scope:1", "text", "m1", updated_by="u1")
    tmp_store.set_scope_model_override("scope:1", "vision", "v1", updated_by="u1")
    assert tmp_store.get_scope_model_overrides("scope:1") == {
        "text_model": "m1",
        "vision_model": "v1",
    }
    # 清单槽
    assert tmp_store.clear_scope_model_override("scope:1", "text") is True
    assert tmp_store.get_scope_model_overrides("scope:1") == {
        "text_model": "",
        "vision_model": "v1",
    }
    # 清整行
    assert tmp_store.clear_scope_model_override("scope:1") is True
    assert tmp_store.get_scope_model_overrides("scope:1") == {
        "text_model": "",
        "vision_model": "",
    }
    # 无覆盖时返回 False
    assert tmp_store.clear_scope_model_override("scope:1") is False


# ------------------------------------------------------------ JSON 迁移


# ------------------------------------------------------------ AIConfig env 挂载


def test_ai_config_from_env_file_and_vars(tmp_path):
    """AI_* env（文件 + 环境变量）→ AIConfig：默认 provider、代理、数值/布尔强转。"""
    from hoshino.ai.config import load_ai_config_from_env

    env_file = tmp_path / ".env.prod"
    env_file.write_text(
        "# AI 配置\n"
        "AI_DEFAULT_PROVIDER=opencode-go\n"
        "AI_PROXY=http://127.0.0.1:7890\n"
        "AI_MAX_HISTORY_MESSAGES=40\n"
        "AI_WEB_SEARCH_NATIVE=false\n"
        "OTHER=ignored\n",
        encoding="utf-8",
    )
    cfg = load_ai_config_from_env(env={"AI_TOOL_MAX_RETRIES": "5"}, env_file=str(env_file))
    assert cfg.default == "opencode-go"
    assert cfg.proxy == "http://127.0.0.1:7890"
    assert cfg.max_history_messages == 40
    assert cfg.web_search_native is False  # 布尔强转
    assert cfg.tool_max_retries == 5  # 环境变量覆盖文件
    # 未配置字段用代码默认
    assert cfg.render_theme == "light"
    # env 显式置空会覆盖文件值 → 字段视为未设置，落代码默认
    cfg2 = load_ai_config_from_env(env={"AI_DEFAULT_PROVIDER": ""}, env_file=str(env_file))
    assert cfg2.default == ""


def test_hsnconfig_ai_mounted_from_env(monkeypatch):
    """config.ai 惰性挂载：从注入的 AI_* env 构建 AIConfig；DB 默认覆盖 env 默认。

    注入的 AI_* 环境变量优先于 ``.env.prod``（见 hoshino/ai/config.py），
    断言注入的测试值，不依赖本机 ``.env.prod``。
    """
    import hoshino.ai.config as ai_config
    from hoshino.ai.base import get_config

    monkeypatch.setenv("AI_DEFAULT_PROVIDER", "test-provider")
    monkeypatch.setenv("AI_PROXY", "http://127.0.0.1:7890")
    monkeypatch.setenv("AI_MAX_HISTORY_MESSAGES", "40")

    # 直接测挂载函数（避免全局 config 实例依赖真实 .env.prod）
    class _FakeHsn:
        pass

    ai_config.mount_into_hsnconfig(_FakeHsn)
    assert "ai" in _FakeHsn.__dict__  # property 已挂
    # 幂等
    ai_config.mount_into_hsnconfig(_FakeHsn)
    assert len([k for k in _FakeHsn.__dict__ if k == "ai"]) == 1

    # get_config：注入的 env 默认 + DB 覆盖
    cfg = get_config()
    assert cfg.default == "test-provider"
    assert cfg.proxy == "http://127.0.0.1:7890"
    assert cfg.max_history_messages == 40
    tmp_store_global = __import__("hoshino.ai.store", fromlist=["set_global_value"])
    tmp_store_global.set_global_value("default_provider", "other")
    try:
        assert get_config().default == "other"
    finally:
        tmp_store_global.clear_global_value("default_provider")
