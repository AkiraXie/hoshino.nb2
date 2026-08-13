"""persona 领域层测试：prompt 模板、三级解析、CRUD 与绑定。"""

from __future__ import annotations

import pytest

from hoshino.modules.ai.config import AIConfig

pytestmark = pytest.mark.usefixtures("_clear_uninfo_cache")


def test_build_prompt_template():
    from hoshino.modules.ai.persona import build_prompt

    p = build_prompt("爱丽丝", "女性", "温柔善良", "测试简介")
    assert p == "你是 爱丽丝，女性。温柔善良。\n测试简介"
    assert build_prompt("爱丽丝") == "你是 爱丽丝。"


def test_resolve_prompt_fallback(tmp_store):
    """无绑定/无全局时回退 AIConfig.system_prompt。"""
    from hoshino.modules.ai.persona import resolve_prompt

    config = AIConfig(system_prompt="默认提示词")
    assert resolve_prompt(None, config) == "默认提示词"
    assert resolve_prompt("milky:1", config) == "默认提示词"


def test_resolve_prompt_global(tmp_store):
    from hoshino.modules.ai import persona

    config = AIConfig(system_prompt="默认提示词")
    persona.create_persona("全局", gender="机器人", personality="稳重", description="g")
    assert persona.set_global("全局") is True
    expected = persona.build_prompt("全局", "机器人", "稳重", "g")
    assert persona.resolve_prompt("milky:1", config) == expected
    assert persona.resolve_prompt(None, config) == expected


def test_resolve_prompt_scope_beats_global(tmp_store):
    """优先级：scope 级 > 全局级 > 默认级。"""
    from hoshino.modules.ai import persona

    config = AIConfig(system_prompt="默认提示词")
    persona.create_persona("全局", gender="机器人", personality="稳重", description="g")
    persona.create_persona("本群", gender="猫娘", personality="活泼", description="s")
    persona.set_global("全局")
    persona.bind_scope("milky:1", "本群")
    assert persona.resolve_prompt("milky:1", config) == persona.build_prompt(
        "本群", "猫娘", "活泼", "s"
    )
    # 未绑定的 scope 走全局
    assert persona.resolve_prompt("milky:2", config) == persona.build_prompt(
        "全局", "机器人", "稳重", "g"
    )


def test_resolve_prompt_dangling_scope_binding_falls_back(tmp_store):
    """scope 绑定指向已删除 persona 时回退下一级。"""
    from hoshino.modules.ai import persona

    config = AIConfig(system_prompt="默认提示词")
    persona.create_persona("幽灵", gender="机器人", personality="稳重", description="g")
    persona.bind_scope("milky:1", "幽灵")
    persona.delete_persona("幽灵")  # 删除时清理绑定引用
    assert persona.resolve_prompt("milky:1", config) == "默认提示词"


def test_persona_crud(tmp_store):
    from hoshino.modules.ai import persona

    created = persona.create_persona(
        "小爱", gender="女性", personality="温柔", description="测试人格"
    )
    assert created["name"] == "小爱"
    assert "温柔" in created["prompt"]
    assert persona.get_persona("小爱") is not None

    updated = persona.update_persona("小爱", personality="活泼")
    assert updated is not None
    assert "活泼" in updated["prompt"]
    assert "温柔" not in updated["prompt"]

    assert persona.update_persona("不存在", personality="x") is None
    assert persona.delete_persona("小爱") is True
    assert persona.get_persona("小爱") is None


def test_bind_missing_persona_returns_false(tmp_store):
    from hoshino.modules.ai import persona

    assert persona.bind_scope("milky:1", "不存在") is False
    assert persona.set_global("不存在") is False


def test_clear_scope_and_global(tmp_store):
    from hoshino.modules.ai import persona

    persona.create_persona("小爱", gender="女性", personality="温柔", description="d")
    persona.bind_scope("milky:1", "小爱")
    assert persona.clear_scope("milky:1") is True
    assert persona.clear_scope("milky:1") is False

    persona.set_global("小爱")
    assert persona.clear_global() is True
    assert persona.clear_global() is False


def test_missing_traits():
    from hoshino.modules.ai.persona import missing_traits

    assert missing_traits("", "", "") == "创建人格需补充：性别、性格、简介"
    assert missing_traits("女", "温", "d") == ""
