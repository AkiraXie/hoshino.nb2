"""AI 工具注册/动态解析与核心工具行为测试。

不连接真实模型：工具函数用假 ctx（仅暴露 ``.deps``）直接调用，验证类别过滤、
live-event 依赖、task profile 恢复、chat surface 的静态 high-risk 排除，以及
core 工具内部的权限复核与 store 读写。
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from nonebot_plugin_alconna.uniseg import Target

from hoshino.modules.ai.config import AIConfig
from hoshino.modules.ai.deps import AgentDeps, PermissionSnapshot, Telemetry

pytestmark = pytest.mark.usefixtures("_clear_uninfo_cache")


def _deps(
    scope_key: str = "milky:1",
    *,
    surface: str = "chat",
    event=None,
    bot=None,
    task=None,
    permissions: PermissionSnapshot | None = None,
) -> AgentDeps:
    return AgentDeps(
        surface=surface,  # type: ignore[arg-type]
        scope_key=scope_key,
        target=Target(id="123"),
        config=AIConfig(),
        permissions=permissions
        or PermissionSnapshot(user_id="u1", is_superuser=False, is_admin=True),
        bot=bot,
        event=event,
        telemetry=Telemetry(provider_id="openai", scope_key=scope_key or "", model="m"),
        task=task,
    )


def _ctx(deps: AgentDeps) -> SimpleNamespace:
    return SimpleNamespace(deps=deps)


def _names(tools) -> set[str]:
    """收集工具可读名：函数取 __name__，pydantic_ai Tool 取 .name。"""
    return {
        getattr(t, "__name__", None) or getattr(t, "name", type(t).__name__)
        for t in tools
    }


# ------------------------------------------------------- resolve_tools


def test_resolve_tools_default_categories(tmp_store):
    """未配置类别的 scope 用安全默认 core/web/skill；high-risk 不注入 chat。"""
    from hoshino.modules.ai.tools import resolve_tools

    names = _names(resolve_tools(_deps()))
    assert {"memory", "persona_manage", "skill_read"} <= names
    assert "now" in names
    # 静态 high-risk 的 shell/Python 不注入 chat
    assert "bash" not in names
    assert "python" not in names
    # computer/bot 不在安全默认
    assert "file" not in names
    assert "send_message" not in names
    assert "service_manage" not in names


def test_resolve_tools_explicit_categories(tmp_store):
    """显式绑定后只用启用类别；关闭项不出现。"""
    from hoshino.modules.ai.tools import resolve_tools

    tmp_store.set_scope_tool_binding("milky:1", "core", "chat", True)
    tmp_store.set_scope_tool_binding("milky:1", "web", "chat", False)
    names = _names(resolve_tools(_deps()))
    assert "memory" in names
    assert "persona_manage" in names
    # web 显式关闭、skill/computer/bot 未绑定 → 不出现
    assert "skill_read" not in names
    assert "web_fetch" not in names
    assert "file" not in names


def test_resolve_tools_computer_only_low_risk_in_chat(tmp_store):
    """chat surface 放行 computer 的 file，但 bash/python 仍被静态风险排除。"""
    from hoshino.modules.ai.tools import resolve_tools

    tmp_store.set_scope_tool_binding("milky:1", "computer", "chat", True)
    names = _names(resolve_tools(_deps()))
    assert "file" in names
    assert "bash" not in names
    assert "python" not in names
    assert "memory" not in names  # 显式类别后只含 computer


def test_resolve_tools_bot_requires_live_event(tmp_store):
    from hoshino.modules.ai.tools import resolve_tools

    tmp_store.set_scope_tool_binding("milky:1", "bot", "chat", True)
    # 无 live event（task 恢复等场景）→ bot 工具不注入
    assert _names(resolve_tools(_deps(event=None))) == set()
    names = _names(resolve_tools(_deps(event=object())))
    assert "send_message" in names
    assert "service_manage" in names


def test_resolve_tools_task_restores_profile():
    """task 恢复只按冻结的 tool_profile 展开，不按当前 category。"""
    from hoshino.modules.ai.tools import resolve_tools

    task = SimpleNamespace(tool_profile={("now", 1)})
    names = _names(resolve_tools(_deps(surface="task", task=task)))
    assert names == {"now"}


# ------------------------------------------------------- core 工具


async def test_memory_tool_scope_isolated(tmp_store):
    from hoshino.modules.ai.tools.core.memory import memory

    ctx = _ctx(_deps("milky:1"))
    assert "已写入" in await memory(ctx, "set", key="k", value="v")
    assert await memory(ctx, "get", key="k") == "v"
    assert "已删除" in await memory(ctx, "delete", key="k")
    assert "暂无" in await memory(ctx, "list")
    # scope 隔离：别的会话读不到
    ctx2 = _ctx(_deps("milky:2"))
    assert "不存在" in await memory(ctx2, "get", key="k")


async def test_memory_tool_value_limit(tmp_store):
    from hoshino.modules.ai.tools.core.memory import memory

    ctx = _ctx(_deps("milky:1"))
    out = await memory(ctx, "set", key="big", value="x" * 2001)
    assert "超过" in out
    assert await memory(ctx, "get", key="big") == "记忆 `big` 不存在。"


async def test_persona_manage_use_requires_admin(tmp_store):
    from hoshino.modules.ai import persona
    from hoshino.modules.ai.tools.core.persona_manage import persona_manage

    persona.create_persona(
        "爱丽丝", gender="女性", personality="温柔", description="测试"
    )
    deps = _deps(
        permissions=PermissionSnapshot(user_id="u1", is_superuser=False, is_admin=False)
    )
    out = await persona_manage(_ctx(deps), "use", name="爱丽丝")
    assert "需要群管理员权限" in out


async def test_persona_manage_use_admin_binds(tmp_store):
    from hoshino.modules.ai import persona
    from hoshino.modules.ai.tools.core.persona_manage import persona_manage

    persona.create_persona(
        "爱丽丝", gender="女性", personality="温柔", description="测试"
    )
    out = await persona_manage(_ctx(_deps()), "use", name="爱丽丝")
    assert "已绑定" in out
    assert tmp_store.get_scope_persona_id("milky:1") is not None
    # 不存在的 persona
    out = await persona_manage(_ctx(_deps()), "use", name="幽灵")
    assert "不存在" in out


async def test_persona_manage_global_delete_rejected(tmp_store):
    """global/delete 仅能通过 admin command，工具内直接拒绝并引导。"""
    from hoshino.modules.ai import persona
    from hoshino.modules.ai.tools.core.persona_manage import persona_manage

    persona.create_persona(
        "爱丽丝", gender="女性", personality="温柔", description="测试"
    )
    out = await persona_manage(_ctx(_deps()), "global", name="爱丽丝")
    assert "仅可通过" in out
    out = await persona_manage(_ctx(_deps()), "delete", name="爱丽丝")
    assert "仅可通过" in out


# ------------------------------------------------------- bot 工具


async def test_send_message_single_emit(monkeypatch):
    """send_message 只调一次 send_to_event，不额外副作用。"""
    from hoshino.modules.ai.tools.bot.send_message import send_message

    calls: list[str] = []

    async def fake_send_to_event(bot, event, message):
        calls.append(message)

    monkeypatch.setattr("hoshino.platform.send_to_event", fake_send_to_event)
    deps = _deps(event=object(), bot=object())
    out = await send_message(_ctx(deps), "目标信息")
    assert out == "消息已发送。"
    assert calls == ["目标信息"]


async def test_send_message_requires_live_event(monkeypatch):
    from hoshino.modules.ai.tools.bot.send_message import send_message

    calls: list[str] = []

    async def fake_send_to_event(bot, event, message):
        calls.append(message)

    monkeypatch.setattr("hoshino.platform.send_to_event", fake_send_to_event)
    out = await send_message(_ctx(_deps()), "hi")  # bot/event 均 None
    assert "不支持" in out
    assert calls == []


async def test_send_message_length_limit(monkeypatch):
    from hoshino.modules.ai.tools.bot.send_message import send_message

    calls: list[str] = []

    async def fake_send_to_event(bot, event, message):
        calls.append(message)

    monkeypatch.setattr("hoshino.platform.send_to_event", fake_send_to_event)
    out = await send_message(_ctx(_deps(event=object(), bot=object())), "x" * 2001)
    assert "过长" in out
    assert calls == []


async def test_service_manage_requires_admin_and_flips_state(tmp_store, monkeypatch):
    from hoshino.modules.ai import base
    from hoshino.modules.ai.tools.bot.service_manage import service_manage

    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(
        base.sv, "set_enable", lambda scope: calls.append(("enable", scope))
    )
    monkeypatch.setattr(
        base.sv, "set_disable", lambda scope: calls.append(("disable", scope))
    )

    # member → 拒绝，不翻转
    member = _deps(
        permissions=PermissionSnapshot(user_id="u", is_superuser=False, is_admin=False)
    )
    out = await service_manage(_ctx(member), "enable")
    assert "需要群管理员权限" in out
    assert calls == []

    # admin → 放行
    admin = _deps(
        permissions=PermissionSnapshot(user_id="u", is_superuser=False, is_admin=True)
    )
    out = await service_manage(_ctx(admin), "disable")
    assert "已停用" in out
    assert calls == [("disable", "milky:1")]


# ------------------------------------------------------- toolset instructions


def test_build_tool_instructions_states(tmp_store):
    from hoshino.modules.ai import prompts, skills
    from hoshino.modules.ai.tools import build_tool_instructions

    # 默认有工具（core/web/skill）→ 含 TOOL_CALL_PROMPT
    parts = build_tool_instructions(_deps())
    assert any(p == prompts.TOOL_CALL_PROMPT for p in parts)

    # 显式绑定 bot 且无 live event → 无工具可注入；技能仍默认启用 → 技能清单
    tmp_store.set_scope_tool_binding("milky:1", "bot", "chat", True)
    parts = build_tool_instructions(_deps(event=None))
    assert not any(p == prompts.TOOL_CALL_PROMPT for p in parts)
    assert any("web_research" in p for p in parts)

    # 再关闭全部技能 → 空
    skills.set_enabled("milky:1", "web_research", False)
    assert build_tool_instructions(_deps(event=None)) == []
