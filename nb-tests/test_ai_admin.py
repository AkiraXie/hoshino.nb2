"""AI 管理插件测试：provider 配置、scope 切换、用量查询、权限。"""

from __future__ import annotations

import itertools
import pytest
from nonebot.adapters.milky import Bot as MilkyBot
from nonebot.adapters.milky.config import ClientInfo
from nonebot.adapters.milky.event import FriendMessageEvent as MilkyPrivateMessageEvent
from nonebot.adapters.milky.event import GroupMessageEvent as MilkyGroupMessageEvent
from nonebot.adapters.milky.model.api import MessageResponse

from hoshino.ai.config import AIConfig

# 本文件复用同一（群、用户）组合做不同 role 的权限断言，必须清 uninfo 会话
# 缓存，见 conftest 中 _clear_uninfo_cache 的说明。
pytestmark = pytest.mark.usefixtures("_clear_uninfo_cache")

# 递增 message_seq 保证 alconna 全局 unimsg_cache 键不跨测试碰撞。起点取
# 300000，高于仓库其他测试的硬编码 seq，避免同 (group, seq) 缓存碰撞。
_seq = itertools.count(300000)


@pytest.fixture(autouse=True)
def _fresh_conversation_manager(monkeypatch):
    """每个测试独立 ConversationManager：单例内存缓存会跨测试残留。"""
    from hoshino.ai import sessions

    manager = sessions.ConversationManager()
    monkeypatch.setattr(sessions, "conversation_manager", manager)
    return manager


# ---------------------------------------------------------------- helpers


def _milky_group(
    text: str,
    *,
    user_id: int = 42,
    role: str = "admin",
    group_id: int = 123456,
) -> tuple[MilkyBot, MilkyGroupMessageEvent]:
    from nonebot import get_adapters
    from nonebot.adapters.milky import Adapter as MilkyAdapter

    adapter = get_adapters()[MilkyAdapter.get_name()]
    bot = MilkyBot(adapter, self_id="10000", info=ClientInfo())
    event = adapter.json_to_event(
        {
            "event_type": "message_receive",
            "time": 1,
            "self_id": 10000,
            "data": {
                "message_scene": "group",
                "peer_id": group_id,
                "message_seq": next(_seq),
                "sender_id": user_id,
                "time": 1,
                "segments": [{"type": "text", "data": {"text": text}}],
                "group": {
                    "group_id": group_id,
                    "group_name": "test group",
                    "member_count": 2,
                    "max_member_count": 100,
                },
                "group_member": {
                    "user_id": user_id,
                    "nickname": "Alice",
                    "sex": "unknown",
                    "group_id": group_id,
                    "card": "Alice member",
                    "title": "",
                    "level": 1,
                    "role": role,
                    "join_time": 1,
                    "last_sent_time": 1,
                },
            },
        }
    )
    assert isinstance(event, MilkyGroupMessageEvent)
    event.to_me = False
    return bot, event


def _milky_private(
    text: str, *, user_id: int = 42
) -> tuple[MilkyBot, MilkyPrivateMessageEvent]:
    from nonebot import get_adapters
    from nonebot.adapters.milky import Adapter as MilkyAdapter

    adapter = get_adapters()[MilkyAdapter.get_name()]
    bot = MilkyBot(adapter, self_id="10000", info=ClientInfo())
    event = adapter.json_to_event(
        {
            "event_type": "message_receive",
            "time": 1,
            "self_id": 10000,
            "data": {
                "message_scene": "friend",
                "peer_id": 999,
                "message_seq": next(_seq),
                "sender_id": user_id,
                "time": 1,
                "segments": [{"type": "text", "data": {"text": text}}],
                "friend": {
                    "user_id": user_id,
                    "nickname": "Alice",
                    "sex": "unknown",
                    "qid": "",
                    "remark": "",
                    "category": {"category_id": 1, "category_name": "默认"},
                },
            },
        }
    )
    assert isinstance(event, MilkyPrivateMessageEvent)
    event.to_me = False
    return bot, event


@pytest.fixture
def tmp_store(tmp_path, monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from hoshino.ai import store

    eng = create_engine(f"sqlite:///{tmp_path / 'aichat.db'}")
    store.Base.metadata.create_all(eng)
    monkeypatch.setattr(store, "engine", eng)
    monkeypatch.setattr(
        store, "Session", sessionmaker(bind=eng, expire_on_commit=False)
    )
    return store


def _stub_env(monkeypatch, tmp_store, *, superuser: bool = True, **overrides):
    """stub ai_admin 的 config / store / superuser 判断，返回 sent 与 saved。

    ``superuser`` 同时控制 NoneBot 权限的 ``config.superusers``（matcher 的
    ``SUPERUSER`` 权限读取它）与 handler 内的 ``is_superuser``，保证平台无关
    权限判断在测试中真实生效。
    """
    from nonebot import get_driver

    from hoshino.modules.ai import ai_admin

    users = {"42"} if superuser else set()
    monkeypatch.setattr(get_driver().config, "superusers", set(users))
    # 与 is_superuser 一致：user_id 可能是 int，需要 str() 归一化再比较。
    monkeypatch.setattr(ai_admin, "is_superuser", lambda bot, uid: str(uid) in users)
    # base.py 的 aichat Service 默认关闭（enable_on_default=False），matcher 的
    # check_service rule 会拦截所有命令；测试里显式开启。
    monkeypatch.setattr(ai_admin.sv, "check_enabled", lambda scope: True)

    defaults = dict(default="openai")
    defaults.update(overrides)
    config = AIConfig(**defaults)
    monkeypatch.setattr(ai_admin, "get_config", lambda: config)

    # provider 走 DB（唯一事实源）：预置两个 provider 及其 model-list。
    tmp_store.upsert_provider_row(
        provider_id="openai",
        url="https://api.example.com/v1",
        key="sk-abcdefghij",
        kind="openai_chat",
        default_text_model="gpt-4o-mini",
    )
    tmp_store.upsert_provider_model("openai", "gpt-4o-mini", "text")
    tmp_store.upsert_provider_row(
        provider_id="anthropic",
        url="https://api.anthropic.com",
        key="sk-ant-1234567890",
        kind="anthropic",
        default_text_model="claude-3-5-sonnet",
    )
    tmp_store.upsert_provider_model("anthropic", "claude-3-5-sonnet", "text")

    saved: list[object] = []
    monkeypatch.setattr(
        ai_admin.sv, "save_config", lambda new_config: saved.append(new_config)
    )

    sent: list[tuple[int, object]] = []

    async def fake_send_group_message(self, *, group_id: int, message):
        sent.append((group_id, message))
        return MessageResponse(message_seq=8, time=1)

    async def fake_send_private_message(self, *, user_id: int, message):
        sent.append((user_id, message))
        return MessageResponse(message_seq=8, time=1)

    monkeypatch.setattr(MilkyBot, "send_group_message", fake_send_group_message)
    monkeypatch.setattr(MilkyBot, "send_private_message", fake_send_private_message)
    return config, sent, saved


# ------------------------------------------------------- provider list


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_provider_list_masks_key(monkeypatch, tmp_store):
    _, sent, _ = _stub_env(monkeypatch, tmp_store)

    bot, event = _milky_group("ai provider list")
    await bot.handle_event(event)

    assert len(sent) == 1
    _, message = sent[0]
    text = message.extract_plain_text()
    assert "openai" in text
    assert "anthropic" in text
    assert "sk-abcdefghij" not in text  # key 脱敏
    assert "sk-ant-1234567890" not in text


# ------------------------------------------------------- provider default


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_provider_default_requires_superuser(monkeypatch, tmp_store):
    """非 superuser 无法触发任何 ai 命令（SUPERUSER matcher 直接拦截）。"""
    _, sent, saved = _stub_env(monkeypatch, tmp_store, superuser=False)

    bot, event = _milky_group("ai provider default anthropic")
    await bot.handle_event(event)

    assert saved == []
    assert sent == []  # matcher 拦截，非 superuser 完全无响应


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_provider_default_success(monkeypatch, tmp_store):
    config, sent, saved = _stub_env(monkeypatch, tmp_store, superuser=True)

    bot, event = _milky_group("ai provider default anthropic")
    await bot.handle_event(event)

    assert len(saved) == 1
    new_config = saved[0]
    assert isinstance(new_config, AIConfig)
    assert new_config.default == "anthropic"
    assert "已设置全局默认 provider" in sent[0][1].extract_plain_text()


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_provider_default_unknown_id(monkeypatch, tmp_store):
    _, sent, saved = _stub_env(monkeypatch, tmp_store)

    bot, event = _milky_group("ai provider default ghost")
    await bot.handle_event(event)

    assert saved == []
    assert "不存在" in sent[0][1].extract_plain_text()


# ------------------------------------------------------- provider use / reset


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_provider_use_binds_scope(monkeypatch, tmp_store):
    _, sent, _ = _stub_env(monkeypatch, tmp_store)

    bot, event = _milky_group("ai provider use anthropic", user_id=42)
    await bot.handle_event(event)

    assert tmp_store.get_scope_provider("milky:123456") == "anthropic"
    assert "已切换到" in sent[0][1].extract_plain_text()


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_provider_use_rejected_in_private(monkeypatch, tmp_store):
    _, sent, _ = _stub_env(monkeypatch, tmp_store)

    bot, event = _milky_private("ai provider use anthropic")
    await bot.handle_event(event)

    assert len(sent) == 1
    assert "私聊不允许" in sent[0][1].extract_plain_text()
    assert tmp_store.get_scope_provider("milky:private:999") is None


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_provider_use_member_rejected(monkeypatch, tmp_store):
    # role=member 且非 SUPERUSER → 不满足 SUPERUSER permission → matcher 不执行
    _, sent, _ = _stub_env(monkeypatch, tmp_store, superuser=False)

    bot, event = _milky_group("ai provider use anthropic", user_id=42, role="member")
    await bot.handle_event(event)

    assert sent == []
    assert tmp_store.get_scope_provider("milky:123456") is None


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_provider_reset_clears_scope(monkeypatch, tmp_store):
    tmp_store.set_scope_provider("milky:123456", "anthropic")
    _, sent, _ = _stub_env(monkeypatch, tmp_store)

    bot, event = _milky_group("ai provider reset")
    await bot.handle_event(event)

    assert tmp_store.get_scope_provider("milky:123456") is None
    assert "已清除" in sent[0][1].extract_plain_text()


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_provider_reset_rejected_in_private(monkeypatch, tmp_store):
    _, sent, _ = _stub_env(monkeypatch, tmp_store)

    bot, event = _milky_private("ai provider reset")
    await bot.handle_event(event)

    assert len(sent) == 1
    assert "私聊不允许" in sent[0][1].extract_plain_text()


# ------------------------------------------------------- provider add / remove


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_provider_add_requires_superuser(monkeypatch, tmp_store):
    _, sent, saved = _stub_env(monkeypatch, tmp_store, superuser=False)

    bot, event = _milky_group("ai status")
    await bot.handle_event(event)

    assert saved == []
    assert sent == []  # 非超管连只读的 ai status 也无响应


@pytest.mark.usefixtures("_nonebot_bootstrap")
# ------------------------------------------------------- scope 模型命令


def _stub_models(monkeypatch, models: list[str] | None):
    """stub provider.fetch_available_models：None 表示网络失败。"""
    from hoshino.modules.ai import ai_admin

    async def fake_fetch(record, *, proxy=None, verify=None, timeout=None):
        return models

    monkeypatch.setattr(ai_admin.provider, "fetch_available_models", fake_fetch)


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_model_shows_current_models(monkeypatch, tmp_store):
    """`ai model`：显示当前文本/多模态模型与操作提示。"""
    _, sent, _ = _stub_env(monkeypatch, tmp_store)

    bot, event = _milky_group("ai model")
    await bot.handle_event(event)

    text = sent[0][1].extract_plain_text()
    assert "gpt-4o-mini" in text  # openai 默认文本模型
    assert "（未设置）" in text  # vision 默认空
    assert "ai model set" in text  # 操作提示


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_model_set_default_slot_is_text(monkeypatch, tmp_store):
    """`ai model set <模型>` 不带槽位默认改文本。"""
    _stub_models(monkeypatch, ["gpt-4o-mini", "gpt-4o"])
    _, sent, _ = _stub_env(monkeypatch, tmp_store)

    bot, event = _milky_group("ai model set gpt-4o")
    await bot.handle_event(event)

    text = sent[0][1].extract_plain_text()
    assert "当前文本模型：`gpt-4o`" in text
    assert "多模态模型：`（未设置）`" in text  # 设完回显两个模型
    assert tmp_store.get_scope_model_overrides("milky:123456")["text_model"] == "gpt-4o"


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_model_set_validates_against_api_list(monkeypatch, tmp_store):
    """模型不在 provider API 可用列表时拒绝，并给出可用列表。"""
    _stub_models(monkeypatch, ["gpt-4o-mini", "gpt-4o"])
    _, sent, _ = _stub_env(monkeypatch, tmp_store)

    bot, event = _milky_group("ai model set text ghost-1")
    await bot.handle_event(event)

    text = sent[0][1].extract_plain_text()
    assert "不在 provider" in text
    assert "gpt-4o-mini" in text  # 可用列表提示
    assert tmp_store.get_scope_model_overrides("milky:123456")["text_model"] == ""


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_model_set_proceeds_when_api_down(monkeypatch, tmp_store):
    """无法连接 provider 时放行并附警告。"""
    _stub_models(monkeypatch, None)
    _, sent, _ = _stub_env(monkeypatch, tmp_store)

    bot, event = _milky_group("ai model set text gpt-4o")
    await bot.handle_event(event)

    text = sent[0][1].extract_plain_text()
    assert "无法连接 provider 校验" in text
    assert "当前文本模型：`gpt-4o`" in text


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_model_set_vision_and_disable(monkeypatch, tmp_store):
    """`ai model set vision <m>` 设置多模态；`vision none` 禁用；reset 清除并回显。"""
    _stub_models(monkeypatch, ["gpt-4o-mini", "gpt-4o"])
    _, sent, _ = _stub_env(monkeypatch, tmp_store)

    bot, event = _milky_group("ai model set vision gpt-4o")
    await bot.handle_event(event)
    text = sent[0][1].extract_plain_text()
    assert "多模态模型：`gpt-4o`" in text
    assert (
        tmp_store.get_scope_model_overrides("milky:123456")["vision_model"] == "gpt-4o"
    )

    bot, event = _milky_group("ai model set vision none")
    await bot.handle_event(event)
    assert tmp_store.get_scope_model_overrides("milky:123456")["vision_model"] == "none"

    bot, event = _milky_group("ai model reset")
    await bot.handle_event(event)
    assert tmp_store.get_scope_model_overrides("milky:123456") == {
        "text_model": "",
        "vision_model": "",
    }


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_model_set_rejected_in_private(monkeypatch, tmp_store):
    _, sent, _ = _stub_env(monkeypatch, tmp_store)

    bot, event = _milky_private("ai model set text gpt-4o-mini")
    await bot.handle_event(event)

    assert "仅限群聊" in sent[0][1].extract_plain_text()


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_model_set_member_rejected(monkeypatch, tmp_store):
    # role=member 且非 SUPERUSER → 不满足 SUPERUSER permission → matcher 不执行
    _, sent, _ = _stub_env(monkeypatch, tmp_store, superuser=False)

    bot, event = _milky_group(
        "ai model set text gpt-4o-mini", user_id=42, role="member"
    )
    await bot.handle_event(event)

    assert len(sent) == 0  # SUPERUSER matcher 直接拦截，非超管无响应
    assert tmp_store.get_scope_model_overrides("milky:123456")["text_model"] == ""


# ------------------------------------------------------- status / stats / clear


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_status_shows_minimal_dashboard(monkeypatch, tmp_store):
    """ai status 只显示当前 provider/文本/多模态，不暴露代理、渲染等配置细节。"""
    tmp_store.set_scope_provider("milky:123456", "anthropic")
    _, sent, _ = _stub_env(monkeypatch, tmp_store)

    bot, event = _milky_group("ai status")
    await bot.handle_event(event)

    text = sent[0][1].extract_plain_text()
    assert "当前 provider：`anthropic`" in text
    assert "文本模型：`claude-3-5-sonnet`" in text
    assert "多模态模型：`（未设置）`" in text
    # 极简看板：不暴露代理/渲染/历史限制等
    assert "代理" not in text
    assert "渲染" not in text
    assert "64 条" not in text
    assert "provider 数量" not in text


@pytest.mark.usefixtures("_nonebot_bootstrap")
@pytest.mark.usefixtures("_nonebot_bootstrap")
@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_stats_aggregates_usage(monkeypatch, tmp_store):
    tmp_store.record_usage_event(
        provider_id="openai",
        scope_key="milky:1",
        model="gpt-4o",
        request_tokens=10,
        response_tokens=5,
        cache_read_tokens=30,
        latency_ms=100.0,
    )
    _, sent, _ = _stub_env(monkeypatch, tmp_store)

    bot, event = _milky_group("ai stats")
    await bot.handle_event(event)

    text = sent[0][1].extract_plain_text()
    assert "openai" in text or "全部 provider" in text
    assert "总 token" in text
    assert "命中率" in text


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_clear_current_scope(monkeypatch, tmp_store):
    from hoshino.ai import sessions

    manager = sessions.conversation_manager
    manager.get_active("milky:123456")  # 自动建「默认」对话
    manager.append_prompt_only("milky:123456", "hi", "openai")
    _, sent, _ = _stub_env(monkeypatch, tmp_store)

    bot, event = _milky_group("ai clear")
    await bot.handle_event(event)

    assert "已清理" in sent[0][1].extract_plain_text()
    assert manager.get_active("milky:123456").messages == []


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_clear_explicit_scope(monkeypatch, tmp_store):
    from hoshino.ai import sessions

    manager = sessions.conversation_manager
    manager.get_active("milky:777")
    manager.append_prompt_only("milky:777", "hi", "openai")
    _, sent, _ = _stub_env(monkeypatch, tmp_store)

    bot, event = _milky_group("ai clear milky:777")
    await bot.handle_event(event)

    assert "已清理" in sent[0][1].extract_plain_text()
    assert manager.get_active("milky:777").messages == []


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_contexts_lists_conversations(monkeypatch, tmp_store):
    from hoshino.ai import sessions

    manager = sessions.conversation_manager
    manager.get_active("milky:123456")
    manager.create("milky:123456", "调研")
    _, sent, _ = _stub_env(monkeypatch, tmp_store)

    bot, event = _milky_group("ai contexts")
    await bot.handle_event(event)

    text = sent[0][1].extract_plain_text()
    assert "默认" in text
    assert "调研" in text
    assert "* 调研" in text  # 最新创建的为激活对话


@pytest.mark.usefixtures("_nonebot_bootstrap")
# ------------------------------------------------------- tools / persona 命令


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_tools_list_shows_defaults(monkeypatch, tmp_store):
    _, sent, _ = _stub_env(monkeypatch, tmp_store)

    bot, event = _milky_group("ai tools list")
    await bot.handle_event(event)

    text = sent[0][1].extract_plain_text()
    assert "本群可用工具" in text
    assert "core" in text  # 类别名保持原始值
    assert "web" in text
    assert "skill" in text
    assert "memory" in text  # 工具名保持原始值
    assert "duckduckgo_search" in text
    assert "skill_read" in text
    assert "milky:123456" not in text  # 不向用户暴露 scope key
    assert "surface" not in text  # 不向用户暴露 surface 概念


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_tools_on_binds_category(monkeypatch, tmp_store):
    _, sent, _ = _stub_env(monkeypatch, tmp_store)

    bot, event = _milky_group("ai tools on computer chat")
    await bot.handle_event(event)

    assert "已开启" in sent[0][1].extract_plain_text()
    bindings = tmp_store.list_scope_tool_bindings("milky:123456", "chat")
    assert {"computer": True} == {b["category"]: b["enabled"] for b in bindings}


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_tools_set_requires_superuser(monkeypatch, tmp_store):
    _, sent, _ = _stub_env(monkeypatch, tmp_store, superuser=False)

    bot, event = _milky_group("ai tools off core chat")
    await bot.handle_event(event)

    assert sent == []  # SUPERUSER matcher 拦截
    assert tmp_store.list_scope_tool_bindings("milky:123456", "chat") == []


@pytest.mark.usefixtures("_nonebot_bootstrap")
@pytest.mark.usefixtures("_nonebot_bootstrap")
@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_permission_snapshot_admin_roles(monkeypatch, tmp_store):
    """build_permission_snapshot 按 uninfo role.id 识别 admin/owner，member 否。"""
    from nonebot import get_driver

    from hoshino.ai import deps as ai_deps

    monkeypatch.setattr(get_driver().config, "superusers", set())

    bot, event = _milky_group("x", role="admin", user_id=42)
    snap = await ai_deps.build_permission_snapshot(bot, event)
    assert snap.is_admin is True and snap.is_superuser is False

    bot, event = _milky_group("x", role="owner", user_id=43)
    snap = await ai_deps.build_permission_snapshot(bot, event)
    assert snap.is_admin is True

    bot, event = _milky_group("x", role="member", user_id=44)
    snap = await ai_deps.build_permission_snapshot(bot, event)
    assert snap.is_admin is False


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_persona_global_requires_superuser(monkeypatch, tmp_store):
    _, sent, _ = _stub_env(monkeypatch, tmp_store, superuser=False)

    bot, event = _milky_group("ai persona global 小爱")
    await bot.handle_event(event)

    assert sent == []  # SUPERUSER matcher 拦截
    assert tmp_store.get_global_value("global_persona") is None


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_task_commands_require_superuser(monkeypatch, tmp_store):
    """ai task 命令（含 workspaces）全部仅 SUPERUSER 可用，非超管被 matcher 拦截。"""
    _, sent, _ = _stub_env(monkeypatch, tmp_store, superuser=False)

    bot, event = _milky_group("ai task workspaces", role="admin", user_id=42)
    await bot.handle_event(event)
    assert sent == []  # 非超管（含 ADMIN）无响应

    bot, event = _milky_group("ai task list", role="member", user_id=43)
    await bot.handle_event(event)
    assert sent == []


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_task_list_superuser_sees_all(monkeypatch, tmp_store):
    """ai task 命令仅超管可用；超管能看到全部 Task。"""
    from test_ai_task import _create_task

    _, sent, _ = _stub_env(monkeypatch, tmp_store, superuser=True)
    _create_task(tmp_store, task_id="t_mine", creator_id="43")
    _create_task(tmp_store, task_id="t_other", creator_id="7")

    bot, event = _milky_group("ai task list", role="member", user_id=42)
    await bot.handle_event(event)
    text = sent[-1][1].extract_plain_text()
    assert "t_mine" in text
    assert "t_other" in text

    # ADMIN：见本 scope 全部
    bot, event = _milky_group("ai task list", role="admin")
    await bot.handle_event(event)
    text = sent[-1][1].extract_plain_text()
    assert "t_mine" in text
    assert "t_other" in text


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_stats_shows_model_breakdown(monkeypatch, tmp_store):
    tmp_store.record_usage_event(
        provider_id="openai",
        scope_key="milky:1",
        model="gpt-4o",
        request_tokens=10,
        response_tokens=5,
        cache_read_tokens=30,
    )
    tmp_store.record_usage_event(
        provider_id="openai",
        scope_key="milky:1",
        model="gpt-4o-mini",
        request_tokens=1,
        response_tokens=1,
    )
    _, sent, _ = _stub_env(monkeypatch, tmp_store)

    bot, event = _milky_group("ai stats")
    await bot.handle_event(event)

    text = sent[0][1].extract_plain_text()
    assert "按模型统计" in text
    assert "openai/gpt-4o" in text
    assert "openai/gpt-4o-mini" in text
    assert "命中率 75.0%" in text

    bot, event = _milky_group("ai stats openai")
    await bot.handle_event(event)

    text = sent[1][1].extract_plain_text()
    assert "按模型统计" in text
    assert "gpt-4o" in text
    assert "openai/gpt-4o" not in text  # 单 provider 时省略前缀


# ------------------------------------------------------- setup / 裸命令


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_bare_ai_shows_status(monkeypatch, tmp_store):
    """裸 `ai` 显示状态总览而不是命令清单（更自然的入口）。"""
    _, sent, _ = _stub_env(monkeypatch, tmp_store)

    bot, event = _milky_group("ai")
    await bot.handle_event(event)

    text = sent[0][1].extract_plain_text()
    assert "当前 provider" in text
    assert "ai help" in sent[1][1].extract_plain_text()  # 入口附带指引


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_ai_help_shows_usage(monkeypatch, tmp_store):
    _, sent, _ = _stub_env(monkeypatch, tmp_store)

    bot, event = _milky_group("ai help")
    await bot.handle_event(event)

    text = sent[0][1].extract_plain_text()
    assert "仅超级用户" in text
    assert "ai setup" in text


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_setup_one_shot_configures_provider(monkeypatch, tmp_store):
    """ai setup：新增 provider + 注册模型 + 设默认 + 绑定当前群，一步完成。"""
    _, sent, saved = _stub_env(monkeypatch, tmp_store)

    bot, event = _milky_group(
        "ai setup myllm --url http://x/v1 --key sk-mykey --text deepseek-v3 --vision gpt-4o"
    )
    await bot.handle_event(event)

    text = sent[0][1].extract_plain_text()
    assert "已新增 provider `myllm`" in text
    assert "已设为全局默认 provider" in text
    assert "已绑定当前群" in text
    assert "可看图" in text
    # DB 落库
    row = tmp_store.get_provider_row("myllm")
    assert row["default_text_model"] == "deepseek-v3"
    assert row["default_vision_model"] == "gpt-4o"
    assert tmp_store.get_scope_provider("milky:123456") == "myllm"
    assert saved and saved[0].default == "myllm"


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_setup_missing_url_key(monkeypatch, tmp_store):
    _, sent, _ = _stub_env(monkeypatch, tmp_store)

    bot, event = _milky_group("ai setup bad --url http://x")
    await bot.handle_event(event)

    assert "需要 --url 与 --key" in sent[0][1].extract_plain_text()
    assert not tmp_store.has_provider_row("bad")
