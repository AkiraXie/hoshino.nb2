"""persona 领域层测试：三级解析优先级、system prompt 组装、CRUD 与绑定。"""

from __future__ import annotations

import pytest

from hoshino.ai.config import AIConfig

pytestmark = pytest.mark.usefixtures("_clear_uninfo_cache")


def test_resolve_prompt_priority_hierarchy(tmp_store):
    """resolve_prompt 三级优先级整体行为：默认级 → 全局级 → scope>全局 → 悬挂绑定回退。"""
    from hoshino.ai import persona

    config = AIConfig(system_prompt="默认提示词")

    # 默认级：无绑定/无全局
    assert persona.resolve_prompt(None, config) == "默认提示词"
    assert persona.resolve_prompt("milky:1", config) == "默认提示词"

    # 全局级
    persona.create_persona("全局", gender="机器人", personality="稳重", description="g")
    assert persona.set_global("全局") is True
    expected_global = persona.build_prompt("全局", "机器人", "稳重", "g")
    assert persona.resolve_prompt("milky:1", config) == expected_global
    assert persona.resolve_prompt(None, config) == expected_global

    # scope 级覆盖全局
    persona.create_persona("本群", gender="猫娘", personality="活泼", description="s")
    persona.bind_scope("milky:1", "本群")
    assert persona.resolve_prompt("milky:1", config) == persona.build_prompt(
        "本群", "猫娘", "活泼", "s"
    )
    assert persona.resolve_prompt("milky:2", config) == expected_global

    # 悬挂绑定：删除 persona 后回退下一级（此处全局仍存在 → 回退全局级）
    persona.create_persona("幽灵", gender="机器人", personality="稳重", description="g")
    persona.bind_scope("milky:3", "幽灵")
    persona.delete_persona("幽灵")
    assert persona.resolve_prompt("milky:3", config) == expected_global


def test_persona_system_prompt_chat_surface(tmp_store):
    """_persona_system_prompt 在 chat surface 的整体行为：输出规范 + 示例对话 + 变量渲染。"""
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
    assert "参考对话风格" in prompt  # 默认示例对话注入
    assert "用户: 早啊" in prompt

    # 内置 {{date}} 等模板变量被渲染，未知变量回退原文不打断对话
    config2 = AIConfig(system_prompt="今天是{{date}}，在{{group_name}}说话")
    deps2 = SimpleNamespace(task=None, scope_key=None, config=config2, event=None, bot=None)
    prompt2 = asyncio.run(providers._persona_system_prompt(SimpleNamespace(deps=deps2)))
    assert "今天是20" in prompt2
    assert "{{date}}" not in prompt2
    assert "在说话" in prompt2

    bad = AIConfig(system_prompt="{{typo_variable}}你好")
    deps3 = SimpleNamespace(task=None, scope_key=None, config=bad, event=None, bot=None)
    prompt3 = asyncio.run(providers._persona_system_prompt(SimpleNamespace(deps=deps3)))
    assert "{{typo_variable}}你好" in prompt3


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


def test_render_persona_overall():
    """render_persona 整体行为：正常渲染/空值变量/无变量直通/未知变量 fail-loud。"""
    from hoshino.ai.persona import render_persona

    text = "我是{{name}}，今天{{date}}在{{group_name}}"
    out = render_persona(text, {"name": "小夏", "date": "2026-08-14", "group_name": "摸鱼群"})
    assert out == "我是小夏，今天2026-08-14在摸鱼群"
    assert render_persona("在{{group_name}}", {"group_name": ""}) == "在"
    assert render_persona("你好", {}) == "你好"
    with pytest.raises(ValueError):
        render_persona("{{foo}}", {"date": "x"})
    with pytest.raises(ValueError):
        render_persona("{{Bad Name}}", {})


def test_persona_crud(tmp_store):
    """persona CRUD 整体：创建/更新/删除 + traits 合并 + begin_dialogs 字段。"""
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

    # begin_dialogs 字段的 create/update
    p = persona.create_persona("带示例", begin_dialogs=[{"user": "a", "assistant": "b"}])
    assert p["begin_dialogs"] == [{"user": "a", "assistant": "b"}]
    updated = persona.update_persona("带示例", begin_dialogs=[{"user": "c", "assistant": "d"}])
    assert updated["begin_dialogs"] == [{"user": "c", "assistant": "d"}]


def test_parse_dialogs_text_alternating():
    from hoshino.ai.persona import parse_dialogs_text

    text = "用户: 早啊\n爱丽丝: 早呀早呀！\n用户: 报错了\n我: 我康康！\n用户: 没配对的尾巴\n"
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
    assert persona_domain.resolve_dialogs("milky:1") == list(prompts.DEFAULT_BEGIN_DIALOGS)

    # 全局 persona 带示例 → 全局生效
    persona_domain.create_persona(
        "全局人格",
        begin_dialogs=[{"user": "hi", "assistant": "hello~"}],
    )
    persona_domain.set_global("全局人格")
    assert persona_domain.resolve_dialogs("milky:1") == [{"user": "hi", "assistant": "hello~"}]

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
    assert persona_domain.resolve_dialogs("milky:2") == [{"user": "hi", "assistant": "hello~"}]


def test_create_duplicate_persona_raises(tmp_store):
    """重名创建抛 ValueError 且不覆盖原 persona（由入口层转为提示，不崩 matcher）。"""
    from hoshino.ai import persona

    persona.create_persona("小爱", gender="女性", personality="温柔", description="原版")
    with pytest.raises(ValueError, match="已存在"):
        persona.create_persona("小爱", gender="女性", personality="急躁", description="覆盖")
    assert persona.get_persona("小爱")["description"] == "原版"
