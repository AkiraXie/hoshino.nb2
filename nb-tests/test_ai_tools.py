"""AI 工具注册/动态解析与核心工具行为测试。

不连接真实模型：工具函数用假 ctx（仅暴露 ``.deps``）直接调用，验证类别叠加解析、
live-event 依赖、task profile 恢复，以及 core 工具内部的权限复核与 store 读写。
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from nonebot_plugin_alconna.uniseg import Target

from hoshino.ai.config import AIConfig
from hoshino.ai.deps import AgentDeps, PermissionSnapshot, Telemetry

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
    from hoshino.ai.tools import resolve_tools

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
    """显式绑定叠加到默认之上；显式关闭项不出现。"""
    from hoshino.ai.tools import resolve_tools

    tmp_store.set_scope_tool_binding("milky:1", "core", "chat", True)
    tmp_store.set_scope_tool_binding("milky:1", "web", "chat", False)
    names = _names(resolve_tools(_deps()))
    # core 显式开、web 显式关、skill 默认开、computer/bot 默认关
    assert "memory" in names
    assert "persona_manage" in names
    assert "skill_read" in names
    assert "web_fetch" not in names
    assert "file" not in names


def test_resolve_tools_computer_adds_file_only_in_chat(tmp_store):
    """开启 computer 叠加到默认之上：chat 只放行 file，bash/python 仍被静态排除。"""
    from hoshino.ai.tools import resolve_tools

    tmp_store.set_scope_tool_binding("milky:1", "computer", "chat", True)
    names = _names(resolve_tools(_deps()))
    assert "file" in names
    # 静态 high-risk 的 shell/Python 仍不注入 chat
    assert "bash" not in names
    assert "python" not in names
    # 默认类别仍保留（叠加语义）
    assert "memory" in names
    assert "duckduckgo_search" in names
    assert "skill_read" in names


def test_resolve_tools_bot_requires_live_event(tmp_store):
    from hoshino.ai.tools import resolve_tools

    tmp_store.set_scope_tool_binding("milky:1", "bot", "chat", True)
    # 无 live event（task 恢复等场景）→ bot 工具不注入，但默认类别仍可用
    names = _names(resolve_tools(_deps(event=None)))
    assert "send_message" not in names
    assert "service_manage" not in names
    assert "memory" in names  # 默认基础类别仍在
    names = _names(resolve_tools(_deps(event=object())))
    assert "send_message" in names
    assert "service_manage" in names


def test_resolve_tools_task_restores_profile():
    """task 恢复只按冻结的 tool_profile 展开，不按当前 category。"""
    from hoshino.ai.tools import resolve_tools

    task = SimpleNamespace(tool_profile={("now", 1)})
    names = _names(resolve_tools(_deps(surface="task", task=task)))
    assert names == {"now"}


# ------------------------------------------------------- core 工具


async def test_memory_tool_scope_isolated(tmp_store):
    from hoshino.ai.tools.core.memory import memory

    ctx = _ctx(_deps("milky:1"))
    assert "已写入" in await memory(ctx, "set", key="k", value="v")
    assert await memory(ctx, "get", key="k") == "v"
    assert "已删除" in await memory(ctx, "delete", key="k")
    assert "暂无" in await memory(ctx, "list")
    # scope 隔离：别的会话读不到
    ctx2 = _ctx(_deps("milky:2"))
    assert "不存在" in await memory(ctx2, "get", key="k")


async def test_memory_tool_value_limit(tmp_store):
    from hoshino.ai.tools.core.memory import memory

    ctx = _ctx(_deps("milky:1"))
    out = await memory(ctx, "set", key="big", value="x" * 2001)
    assert "超过" in out
    assert await memory(ctx, "get", key="big") == "记忆 `big` 不存在。"


async def test_persona_manage_use_requires_admin(tmp_store):
    from hoshino.ai import persona
    from hoshino.ai.tools.core.persona_manage import persona_manage

    persona.create_persona(
        "爱丽丝", gender="女性", personality="温柔", description="测试"
    )
    deps = _deps(
        permissions=PermissionSnapshot(user_id="u1", is_superuser=False, is_admin=False)
    )
    out = await persona_manage(_ctx(deps), "use", name="爱丽丝")
    assert "需要群管理员权限" in out


async def test_persona_manage_use_admin_binds(tmp_store):
    from hoshino.ai import persona
    from hoshino.ai.tools.core.persona_manage import persona_manage

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
    from hoshino.ai import persona
    from hoshino.ai.tools.core.persona_manage import persona_manage

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
    from hoshino.ai.tools.bot.send_message import send_message

    calls: list[str] = []

    async def fake_send_to_event(bot, event, message):
        calls.append(message)

    monkeypatch.setattr("hoshino.platform.send_to_event", fake_send_to_event)
    deps = _deps(event=object(), bot=object())
    out = await send_message(_ctx(deps), "目标信息")
    assert out == "消息已发送。"
    assert calls == ["目标信息"]


async def test_send_message_requires_live_event(monkeypatch):
    from hoshino.ai.tools.bot.send_message import send_message

    calls: list[str] = []

    async def fake_send_to_event(bot, event, message):
        calls.append(message)

    monkeypatch.setattr("hoshino.platform.send_to_event", fake_send_to_event)
    out = await send_message(_ctx(_deps()), "hi")  # bot/event 均 None
    assert "不支持" in out
    assert calls == []


async def test_send_message_length_limit(monkeypatch):
    from hoshino.ai.tools.bot.send_message import send_message

    calls: list[str] = []

    async def fake_send_to_event(bot, event, message):
        calls.append(message)

    monkeypatch.setattr("hoshino.platform.send_to_event", fake_send_to_event)
    out = await send_message(_ctx(_deps(event=object(), bot=object())), "x" * 2001)
    assert "过长" in out
    assert calls == []


async def test_service_manage_requires_admin_and_flips_state(tmp_store, monkeypatch):
    from hoshino.ai import base
    from hoshino.ai.tools.bot.service_manage import service_manage

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


def test_enabled_task_categories_default_and_explicit(tmp_store):
    """与 resolve_tools 同一叠加语义：默认 + 显式 on。"""
    from hoshino.ai import tools

    assert tools.enabled_task_categories("milky:new") == ["core", "skill", "web"]
    tmp_store.set_scope_tool_binding("milky:new", "computer", "task", True)
    assert tools.enabled_task_categories("milky:new") == [
        "computer",
        "core",
        "skill",
        "web",
    ]


def test_build_tool_instructions_states(tmp_store):
    from hoshino.ai import prompts, skills
    from hoshino.ai.tools import build_tool_instructions

    # 默认有工具（core/web/skill）→ 含 TOOL_CALL_PROMPT
    parts = build_tool_instructions(_deps())
    assert any(p == prompts.TOOL_CALL_PROMPT for p in parts)

    # bot=True + 无 live event → bot 工具不注入，但 core/web/skill 仍在 → 仍含提示
    tmp_store.set_scope_tool_binding("milky:1", "bot", "chat", True)
    parts = build_tool_instructions(_deps(event=None))
    assert any(p == prompts.TOOL_CALL_PROMPT for p in parts)
    assert any("web-research" in p for p in parts)

    # 关闭全部技能 → 技能清单消失，但工具提示仍在（基础/联网类别）
    skills.set_enabled("milky:1", "web-research", False)
    parts = build_tool_instructions(_deps(event=None))
    assert any(p == prompts.TOOL_CALL_PROMPT for p in parts)
    assert not any("web-research" in p for p in parts)


# ------------------------------------------------------- computer/file 工具


def _file_ctx(tmp_path, *, surface: str = "chat") -> SimpleNamespace:
    task = (
        SimpleNamespace(workdir=str(tmp_path), tool_profile=frozenset())
        if surface == "task"
        else None
    )
    deps = AgentDeps(
        surface=surface,  # type: ignore[arg-type]
        scope_key="milky:1",
        target=Target(id="123"),
        config=AIConfig(computer_workdir=str(tmp_path)),
        permissions=PermissionSnapshot(user_id="u1", is_superuser=False, is_admin=True),
        bot=None,
        event=None,
        telemetry=Telemetry(provider_id="openai", scope_key="milky:1", model="m"),
        task=task,
    )
    return SimpleNamespace(deps=deps)


async def test_file_delete_refused_on_chat_surface(tmp_path):
    """chat 不执行 delete（无副作用），引导创建 Task（plan 10：chat 不审批）。"""
    from hoshino.ai.tools.computer.file import file

    ctx = _file_ctx(tmp_path)
    assert "已写入" in await file(ctx, "a.txt", mode="write", content="x")
    out = await file(ctx, "a.txt", mode="delete")
    assert "创建 Task" in out
    assert (tmp_path / "a.txt").exists()


async def test_file_delete_executes_on_task_surface(tmp_path):
    """task surface 的 delete 经 deferred approval 后实际执行（plan 8.1）。"""
    from hoshino.ai.tools.computer.file import file

    ctx = _file_ctx(tmp_path, surface="task")
    await file(ctx, "a.txt", mode="write", content="x")
    out = await file(ctx, "a.txt", mode="delete")
    assert "已删除" in out
    assert not (tmp_path / "a.txt").exists()
    assert "不存在" in await file(ctx, "a.txt", mode="delete")


async def test_file_delete_directory_refused_on_task(tmp_path):
    """目录删除（bulk）不在 v1 范围：拒绝且无副作用。"""
    from hoshino.ai.tools.computer.file import file

    (tmp_path / "sub").mkdir()
    ctx = _file_ctx(tmp_path, surface="task")
    out = await file(ctx, "sub", mode="delete")
    assert "不支持删除目录" in out
    assert (tmp_path / "sub").is_dir()


async def test_file_sensitive_paths_always_refused(tmp_path):
    """.env 等敏感路径任何 mode 都拒绝，审批不能放行（plan 8.1/10）。"""
    from hoshino.ai.tools.computer.file import file

    sensitive = tmp_path / ".env"
    sensitive.write_text("SECRET=1")
    ctx = _file_ctx(tmp_path, surface="task")
    assert "敏感路径" in await file(ctx, ".env", mode="read")
    assert "敏感路径" in await file(ctx, ".env", mode="write", content="x")
    assert "敏感路径" in await file(ctx, ".env", mode="delete")
    assert sensitive.read_text() == "SECRET=1"


async def test_file_containment_blocks_escape(tmp_path):
    """相对路径越出 workspace root 直接拒绝。"""
    from hoshino.ai.tools.computer.file import file

    ctx = _file_ctx(tmp_path, surface="task")
    assert "越出" in await file(ctx, "../../etc/passwd", mode="read")
    assert "越出" in await file(ctx, "../x.txt", mode="write", content="x")


# ------------------------------------------------------- web 工具


async def test_web_fetch_blocks_private_and_non_http():
    """web_fetch 拒绝私有/回环地址与非 http 协议（SSRF 防护）。"""
    from hoshino.ai.tools.web import web_fetch as web_fetch_mod

    if web_fetch_mod.tool is None:
        pytest.skip("markdownify 未安装")
    ctx = _ctx(_deps())
    assert "私有" in await web_fetch_mod.tool(ctx, "http://127.0.0.1/x")
    assert "私有" in await web_fetch_mod.tool(ctx, "http://169.254.169.254/latest")
    assert "仅支持" in await web_fetch_mod.tool(ctx, "file:///etc/passwd")


def test_web_search_prefers_search_over_fetch():
    """web_search 保持原始名，但描述引导优先搜索、少抓全文。"""
    from hoshino.ai.tools.web import web_search as web_search_mod

    if web_search_mod.tool is None:
        pytest.skip("ddgs 未安装")
    assert web_search_mod.tool.name == "duckduckgo_search"
    assert "优先" in web_search_mod.tool.description
