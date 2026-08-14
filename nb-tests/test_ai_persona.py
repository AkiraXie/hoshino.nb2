"""persona 领域层测试：prompt 模板、三级解析、CRUD 与绑定。"""

from __future__ import annotations

import json

import pytest

from hoshino.ai.config import AIConfig

pytestmark = pytest.mark.usefixtures("_clear_uninfo_cache")


def test_build_prompt_template():
    from hoshino.ai.persona import build_prompt

    p = build_prompt("爱丽丝", "女性", "温柔善良", "测试简介")
    assert p == "你是 爱丽丝，女性。温柔善良。\n测试简介"
    assert build_prompt("爱丽丝") == "你是 爱丽丝。"


def test_default_system_prompt_persona_and_style():
    """默认人格是元气少女（朋友式口吻），且带简洁 + 禁止奇怪对比句与黑话的约束。"""
    from hoshino.ai.prompts import DEFAULT_SYSTEM_PROMPT

    for keyword in ("乐观开朗", "阳光明媚", "少女", "好奇心", "元气", "朋友"):
        assert keyword in DEFAULT_SYSTEM_PROMPT
    assert "简洁" in DEFAULT_SYSTEM_PROMPT
    assert "不是xxx而是yyy" in DEFAULT_SYSTEM_PROMPT
    assert "黑话" in DEFAULT_SYSTEM_PROMPT


def test_output_style_rules_loaded():
    """output.md 被加载为强制输出规范，且包含 Markdown 结构与禁用黑话等约束。"""
    from hoshino.ai.prompts import OUTPUT_STYLE_RULES

    assert OUTPUT_STYLE_RULES
    for keyword in (
        "简洁",
        "标题",
        "表格",
        "不是xxx而是yyy",
        "收口",
        "基线",
        "接缝",
        "黑话",
    ):
        assert keyword in OUTPUT_STYLE_RULES


def test_persona_system_prompt_appends_output_rules(tmp_store):
    """系统提示词在 persona 之后追加 Markdown 输出规范（所有 persona 强制生效）。"""
    import asyncio
    from types import SimpleNamespace

    from hoshino.ai import prompts, providers

    config = AIConfig(system_prompt="人格")
    deps = SimpleNamespace(task=None, scope_key=None, config=config)
    ctx = SimpleNamespace(deps=deps)

    prompt = asyncio.run(providers._persona_system_prompt(ctx))
    assert prompt.startswith("人格")
    assert providers.OUTPUT_STYLE_HEADER in prompt  # 自然过渡句拼接输出规范
    assert prompts.OUTPUT_STYLE_RULES in prompt


def test_resolve_prompt_fallback(tmp_store):
    """无绑定/无全局时回退 AIConfig.system_prompt。"""
    from hoshino.ai.persona import resolve_prompt

    config = AIConfig(system_prompt="默认提示词")
    assert resolve_prompt(None, config) == "默认提示词"
    assert resolve_prompt("milky:1", config) == "默认提示词"


def test_resolve_prompt_global(tmp_store):
    from hoshino.ai import persona

    config = AIConfig(system_prompt="默认提示词")
    persona.create_persona("全局", gender="机器人", personality="稳重", description="g")
    assert persona.set_global("全局") is True
    expected = persona.build_prompt("全局", "机器人", "稳重", "g")
    assert persona.resolve_prompt("milky:1", config) == expected
    assert persona.resolve_prompt(None, config) == expected


def test_resolve_prompt_scope_beats_global(tmp_store):
    """优先级：scope 级 > 全局级 > 默认级。"""
    from hoshino.ai import persona

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
    from hoshino.ai import persona

    config = AIConfig(system_prompt="默认提示词")
    persona.create_persona("幽灵", gender="机器人", personality="稳重", description="g")
    persona.bind_scope("milky:1", "幽灵")
    persona.delete_persona("幽灵")  # 删除时清理绑定引用
    assert persona.resolve_prompt("milky:1", config) == "默认提示词"


def test_persona_crud(tmp_store):
    from hoshino.ai import persona

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
    from hoshino.ai import persona

    assert persona.bind_scope("milky:1", "不存在") is False
    assert persona.set_global("不存在") is False


def test_clear_scope_and_global(tmp_store):
    from hoshino.ai import persona

    persona.create_persona("小爱", gender="女性", personality="温柔", description="d")
    persona.bind_scope("milky:1", "小爱")
    assert persona.clear_scope("milky:1") is True
    assert persona.clear_scope("milky:1") is False

    persona.set_global("小爱")
    assert persona.clear_global() is True
    assert persona.clear_global() is False


def test_missing_traits():
    from hoshino.ai.persona import missing_traits

    assert missing_traits("", "", "") == "创建人格需补充：性别、性格、简介"
    assert missing_traits("女", "温", "d") == ""


def test_dialogs_to_json_filters_invalid():
    from hoshino.ai.persona import dialogs_to_json

    assert dialogs_to_json(None) == "[]"
    assert dialogs_to_json([]) == "[]"
    raw = dialogs_to_json(
        [{"user": "早啊", "assistant": "早呀！"}, {"user": "", "assistant": "x"}]
    )
    assert json.loads(raw) == [{"user": "早啊", "assistant": "早呀！"}]


def test_parse_dialogs_text_alternating():
    from hoshino.ai.persona import parse_dialogs_text

    text = (
        "用户: 早啊\n"
        "爱丽丝: 早呀早呀！\n"
        "用户: 报错了\n"
        "我: 我康康！\n"
        "用户: 没配对的尾巴\n"
    )
    dialogs = parse_dialogs_text(text, "爱丽丝")
    assert dialogs == [
        {"user": "早啊", "assistant": "早呀早呀！"},
        {"user": "报错了", "assistant": "我康康！"},
    ]
    assert parse_dialogs_text("", "爱丽丝") == []


def test_resolve_dialogs_hierarchy(tmp_store):
    from hoshino.ai import persona as persona_domain
    from hoshino.ai import prompts

    # 无任何绑定 → 默认内置示例
    assert persona_domain.resolve_dialogs(None) == list(prompts.DEFAULT_BEGIN_DIALOGS)
    assert persona_domain.resolve_dialogs("milky:1") == list(
        prompts.DEFAULT_BEGIN_DIALOGS
    )

    # 全局 persona 带示例 → 全局生效
    persona_domain.create_persona(
        "全局人格",
        begin_dialogs=[{"user": "hi", "assistant": "hello~"}],
    )
    persona_domain.set_global("全局人格")
    assert persona_domain.resolve_dialogs("milky:1") == [
        {"user": "hi", "assistant": "hello~"}
    ]

    # scope persona 带示例 → scope 覆盖全局
    persona_domain.create_persona(
        "群人格",
        begin_dialogs=[{"user": "在吗", "assistant": "在的在的！"}],
    )
    assert persona_domain.bind_scope("milky:1", "群人格")
    assert persona_domain.resolve_dialogs("milky:1") == [
        {"user": "在吗", "assistant": "在的在的！"}
    ]

    # scope persona 无示例 → 回退全局
    persona_domain.create_persona("无示例人格")
    assert persona_domain.bind_scope("milky:2", "无示例人格")
    assert persona_domain.resolve_dialogs("milky:2") == [
        {"user": "hi", "assistant": "hello~"}
    ]


def test_persona_crud_with_dialogs(tmp_store):
    from hoshino.ai import persona as persona_domain

    p = persona_domain.create_persona(
        "带示例",
        begin_dialogs=[{"user": "a", "assistant": "b"}],
    )
    assert p["begin_dialogs"] == [{"user": "a", "assistant": "b"}]

    updated = persona_domain.update_persona(
        "带示例", begin_dialogs=[{"user": "c", "assistant": "d"}]
    )
    assert updated["begin_dialogs"] == [{"user": "c", "assistant": "d"}]


def test_persona_system_prompt_includes_dialogs(tmp_store):
    """chat surface：system prompt 追加「参考对话风格」默认示例对话。"""
    import asyncio
    from types import SimpleNamespace

    from hoshino.ai import prompts, providers

    config = AIConfig(system_prompt="人格")
    deps = SimpleNamespace(task=None, scope_key=None, config=config)
    ctx = SimpleNamespace(deps=deps)

    prompt = asyncio.run(providers._persona_system_prompt(ctx))
    assert prompt.startswith("人格")
    assert "参考对话风格" in prompt
    assert "用户: 早啊" in prompt  # 默认示例对话注入
    assert prompts.OUTPUT_STYLE_RULES in prompt


def test_persona_system_prompt_dialogs_not_injected_for_task(tmp_store):
    """task surface：冻结 persona_prompt，不注入示例对话。"""
    import asyncio
    from types import SimpleNamespace

    from hoshino.ai import providers

    deps = SimpleNamespace(
        task=SimpleNamespace(persona_prompt="任务人格"),
        scope_key=None,
        config=AIConfig(),
    )
    ctx = SimpleNamespace(deps=deps)
    prompt = asyncio.run(providers._persona_system_prompt(ctx))
    assert prompt.startswith("任务人格")
    assert "参考对话风格" not in prompt


def test_render_persona_variables():
    from hoshino.ai.persona import render_persona

    text = "我是{{name}}，今天{{date}}在{{group_name}}"
    out = render_persona(
        text, {"name": "小夏", "date": "2026-08-14", "group_name": "摸鱼群"}
    )
    assert out == "我是小夏，今天2026-08-14在摸鱼群"
    # 空值变量渲染为空串
    assert render_persona("在{{group_name}}", {"group_name": ""}) == "在"
    # 无变量原文直通
    assert render_persona("你好", {}) == "你好"


def test_render_persona_unknown_variable_raises():
    from hoshino.ai.persona import render_persona

    with pytest.raises(ValueError):
        render_persona("{{foo}}", {"date": "x"})
    with pytest.raises(ValueError):
        render_persona("{{Bad Name}}", {})


def test_persona_system_prompt_renders_builtin_variables(tmp_store):
    """chat surface：内置 {{date}} 等模板变量被渲染，未知变量回退原文。"""
    import asyncio
    from types import SimpleNamespace

    from hoshino.ai import providers

    config = AIConfig(system_prompt="今天是{{date}}，在{{group_name}}说话")
    deps = SimpleNamespace(
        task=None, scope_key=None, config=config, event=None, bot=None
    )
    ctx = SimpleNamespace(deps=deps)

    prompt = asyncio.run(providers._persona_system_prompt(ctx))
    assert "今天是20" in prompt  # {{date}} 已渲染为日期
    assert "{{date}}" not in prompt
    assert "在说话" in prompt  # {{group_name}} 无 event → 空串

    # 未知变量：渲染失败回退原文，不打断对话
    bad = AIConfig(system_prompt="{{typo_variable}}你好")
    deps2 = SimpleNamespace(task=None, scope_key=None, config=bad, event=None, bot=None)
    prompt2 = asyncio.run(providers._persona_system_prompt(SimpleNamespace(deps=deps2)))
    assert "{{typo_variable}}你好" in prompt2


def test_create_duplicate_persona_raises(tmp_store):
    """重名创建抛 ValueError 且不覆盖原 persona（由入口层转为提示，不崩 matcher）。"""
    from hoshino.ai import persona

    persona.create_persona(
        "小爱", gender="女性", personality="温柔", description="原版"
    )
    with pytest.raises(ValueError, match="已存在"):
        persona.create_persona(
            "小爱", gender="女性", personality="急躁", description="覆盖"
        )
    assert persona.get_persona("小爱")["description"] == "原版"
