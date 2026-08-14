"""AI provider DB 层测试：三张新表 CRUD 与 aichat.json → DB 迁移。

store 层测试不启动 NoneBot；``tmp_store`` 把 store.engine/Session 指向临时 SQLite。
"""

from __future__ import annotations

import json

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
    tmp_store.upsert_provider_row(
        provider_id="p", default_text_model="b", kind="openai_responses"
    )
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

    tmp_store.upsert_provider_row(
        provider_id="p", kind="openai_chat", default_text_model="default"
    )
    assert provider_domain.resolve_text_model("scope:1", "p") == "default"
    tmp_store.set_scope_model_override("scope:1", "text", "override")
    assert provider_domain.resolve_text_model("scope:1", "p") == "override"


def test_validate_model_choice_checks_capabilities(tmp_store):
    """text 槽要 text/both；vision 槽要 multimodal/both；none 放行。"""
    from hoshino.ai import provider as provider_domain

    tmp_store.upsert_provider_model("p", "t", "text")
    tmp_store.upsert_provider_model("p", "v", "multimodal")
    tmp_store.upsert_provider_model("p", "b", "both")

    assert provider_domain.validate_model_choice("p", "t", "text") is None
    assert provider_domain.validate_model_choice("p", "v", "vision") is None
    assert provider_domain.validate_model_choice("p", "b", "text") is None
    assert provider_domain.validate_model_choice("p", "b", "vision") is None
    assert provider_domain.validate_model_choice("p", "none", "vision") is None

    # 能力不匹配
    assert "不能用作多模态模型" in provider_domain.validate_model_choice(
        "p", "t", "vision"
    )
    assert "不能用作纯文本模型" in provider_domain.validate_model_choice(
        "p", "v", "text"
    )
    # 未注册
    assert "不在" in provider_domain.validate_model_choice("p", "ghost", "text")


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


def _write_json_config(path, providers):
    path.write_text(
        json.dumps({"default": "deepseek", "providers": providers}, ensure_ascii=False),
        encoding="utf-8",
    )


def test_migrate_json_providers_imports_and_clears(tmp_store, tmp_path):
    from hoshino.ai.base import migrate_json_providers

    cfg = tmp_path / "aichat.json"
    _write_json_config(
        cfg,
        {
            "deepseek": {
                "url": "https://api.deepseek.com/anthropic",
                "key": "sk-abc",
                "config": {"kind": "anthropic", "model": "deepseek-v4-flash"},
            },
            "opencode-go": {
                "url": "https://opencode.ai/zen/go/v1",
                "key": "sk-def",
                "config": {"kind": "openai_chat", "model": "deepseek-v4-flash"},
            },
        },
    )
    assert migrate_json_providers(str(cfg)) == 2
    # provider 行
    ds = tmp_store.get_provider_row("deepseek")
    assert ds["kind"] == "anthropic"
    assert ds["default_text_model"] == "deepseek-v4-flash"
    assert ds["default_vision_model"] == ""  # 现有两个 provider 多模态模型为空
    assert ds["key"] == "sk-abc"
    oc = tmp_store.get_provider_row("opencode-go")
    assert oc["kind"] == "openai_chat"
    # model-list 自动注册为 text
    assert (
        tmp_store.get_provider_model("deepseek", "deepseek-v4-flash")["capabilities"]
        == "text"
    )
    # JSON providers 被清空
    raw = json.loads(cfg.read_text(encoding="utf-8"))
    assert raw["providers"] == {}
    assert raw["default"] == "deepseek"  # 其它字段保留


def test_migrate_json_providers_idempotent(tmp_store, tmp_path):
    from hoshino.ai.base import migrate_json_providers

    cfg = tmp_path / "aichat.json"
    _write_json_config(
        cfg,
        {
            "p": {
                "url": "u",
                "key": "k",
                "config": {"kind": "openai_chat", "model": "m"},
            }
        },
    )
    assert migrate_json_providers(str(cfg)) == 1
    # 再跑一次：DB 已有，不重复插入；JSON 已空直接返回 0
    assert migrate_json_providers(str(cfg)) == 0
    assert len(tmp_store.list_provider_rows()) == 1


def test_migrate_json_providers_keeps_existing_db(tmp_store, tmp_path):
    """DB 已有同名 provider 时不覆盖（DB 是事实源）。"""
    from hoshino.ai.base import migrate_json_providers

    tmp_store.upsert_provider_row(
        provider_id="p", default_text_model="db-model", kind="openai_responses"
    )
    cfg = tmp_path / "aichat.json"
    _write_json_config(
        cfg,
        {
            "p": {
                "url": "u",
                "key": "k",
                "config": {"kind": "openai_chat", "model": "json-model"},
            }
        },
    )
    assert migrate_json_providers(str(cfg)) == 0
    row = tmp_store.get_provider_row("p")
    assert row["default_text_model"] == "db-model"
    assert row["kind"] == "openai_responses"


def test_migrate_json_providers_missing_file(tmp_store):
    from hoshino.ai.base import migrate_json_providers

    assert migrate_json_providers("/nonexistent/aichat.json") == 0
