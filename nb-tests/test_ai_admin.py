"""AI 管理插件测试：provider 配置、scope 切换、用量查询、权限。"""

from __future__ import annotations

import os

import pytest
from nonebot.adapters.milky import Bot as MilkyBot
from nonebot.adapters.milky.config import ClientInfo
from nonebot.adapters.milky.event import FriendMessageEvent as MilkyPrivateMessageEvent
from nonebot.adapters.milky.event import GroupMessageEvent as MilkyGroupMessageEvent
from nonebot.adapters.milky.model.api import MessageResponse

from conftest import next_seq
from hoshino.ai.config import AIConfig

# 本文件复用同一（群、用户）组合做不同 role 的权限断言，必须清 uninfo 会话
# 缓存，见 conftest 中 _clear_uninfo_cache 的说明。
pytestmark = pytest.mark.usefixtures("_clear_uninfo_cache")


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
                "message_seq": next_seq(),
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


def _milky_private(text: str, *, user_id: int = 42) -> tuple[MilkyBot, MilkyPrivateMessageEvent]:
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
                "message_seq": next_seq(),
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

    defaults = {"default": "openai"}
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
    monkeypatch.setattr(ai_admin.sv, "save_config", lambda new_config: saved.append(new_config))
    # 全局默认 provider 已改由 DB 持久化（store.AIGlobal["default_provider"]）

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

    assert tmp_store.get_global_value("default_provider") == "anthropic"
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
@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_model_set_default_slot_is_text(monkeypatch, tmp_store):
    """`ai model set <模型>` 不带槽位默认改文本。"""
    _stub_models(monkeypatch, ["gpt-4o-mini", "gpt-4o"])
    _, sent, _ = _stub_env(monkeypatch, tmp_store)

    bot, event = _milky_group("ai model set gpt-4o")
    await bot.handle_event(event)

    text = sent[0][1].extract_plain_text()
    assert "当前文本模型：`gpt-4o`" in text
    assert "ai vision" in text  # 回显附带 vision 引导
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
async def test_vision_set_and_disable(monkeypatch, tmp_store):
    """`ai vision set`：空格/斜杠形式设 provider+模型；none 禁用；reset 清除回退。"""
    _stub_models(monkeypatch, ["gpt-4o-mini", "gpt-4o"])
    _, sent, _ = _stub_env(monkeypatch, tmp_store)

    # 空格形式
    bot, event = _milky_group("ai vision set openai gpt-4o")
    await bot.handle_event(event)
    text = sent[0][1].extract_plain_text()
    assert "当前 vision：`openai` / `gpt-4o`" in text
    assert tmp_store.get_scope_model_overrides("milky:123456")["vision_provider"] == "openai"
    assert tmp_store.get_scope_model_overrides("milky:123456")["vision_model"] == "gpt-4o"

    # 斜杠形式
    bot, event = _milky_group("ai vision set openai/gpt-4o-mini")
    await bot.handle_event(event)
    assert tmp_store.get_scope_model_overrides("milky:123456")["vision_model"] == "gpt-4o-mini"

    # none 禁用
    bot, event = _milky_group("ai vision set none")
    await bot.handle_event(event)
    assert tmp_store.get_scope_model_overrides("milky:123456")["vision_model"] == "none"

    # reset 清除（回退全局默认）
    bot, event = _milky_group("ai vision reset")
    await bot.handle_event(event)
    assert tmp_store.get_scope_model_overrides("milky:123456") == {
        "text_model": "",
        "vision_provider": "",
        "vision_model": "",
    }


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_vision_set_validates_provider_and_model(monkeypatch, tmp_store):
    """vision 模型需在指定 provider 的 API 可用列表内；provider 需存在。"""
    _stub_models(monkeypatch, ["gpt-4o-mini", "gpt-4o"])
    _, sent, _ = _stub_env(monkeypatch, tmp_store)

    bot, event = _milky_group("ai vision set ghost gpt-4o")
    await bot.handle_event(event)
    assert "不存在" in sent[0][1].extract_plain_text()
    assert tmp_store.get_scope_model_overrides("milky:123456")["vision_provider"] == ""

    bot, event = _milky_group("ai vision set openai ghost-1")
    await bot.handle_event(event)
    text = sent[1][1].extract_plain_text()
    assert "不在 provider" in text
    assert tmp_store.get_scope_model_overrides("milky:123456")["vision_model"] == ""


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_vision_default_global(monkeypatch, tmp_store):
    """`ai vision default <provider> <模型>` 写全局默认；none 清除。"""
    from hoshino.ai.provider import VISION_GLOBAL_MODEL, VISION_GLOBAL_PROVIDER

    _stub_models(monkeypatch, ["gpt-4o-mini", "gpt-4o"])
    _, sent, _ = _stub_env(monkeypatch, tmp_store)

    bot, event = _milky_group("ai vision default openai/gpt-4o")
    await bot.handle_event(event)
    text = sent[0][1].extract_plain_text()
    assert "已设置全局默认 vision" in text
    assert tmp_store.get_global_value(VISION_GLOBAL_PROVIDER) == "openai"
    assert tmp_store.get_global_value(VISION_GLOBAL_MODEL) == "gpt-4o"

    bot, event = _milky_group("ai vision default none")
    await bot.handle_event(event)
    assert tmp_store.get_global_value(VISION_GLOBAL_PROVIDER) is None
    assert tmp_store.get_global_value(VISION_GLOBAL_MODEL) is None


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_vision_status_shows_source(monkeypatch, tmp_store):
    """`ai vision` 显示当前生效配置与来源（本群配置/全局默认/未配置）。"""
    from hoshino.ai.provider import VISION_GLOBAL_MODEL, VISION_GLOBAL_PROVIDER

    _, sent, _ = _stub_env(monkeypatch, tmp_store)
    bot, event = _milky_group("ai vision")
    await bot.handle_event(event)
    assert "（未配置）" in sent[0][1].extract_plain_text()

    tmp_store.set_global_value(VISION_GLOBAL_PROVIDER, "openai")
    tmp_store.set_global_value(VISION_GLOBAL_MODEL, "gpt-4o")
    bot, event = _milky_group("ai vision")
    await bot.handle_event(event)
    text = sent[1][1].extract_plain_text()
    assert "`openai` / `gpt-4o`" in text
    assert "全局默认" in text

    tmp_store.set_scope_vision("milky:123456", "openai", "gpt-4o-mini")
    bot, event = _milky_group("ai vision")
    await bot.handle_event(event)
    text = sent[2][1].extract_plain_text()
    assert "`openai` / `gpt-4o-mini`" in text
    assert "本群配置" in text


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_vision_set_rejected_in_private(monkeypatch, tmp_store):
    _, sent, _ = _stub_env(monkeypatch, tmp_store)

    bot, event = _milky_private("ai vision set openai gpt-4o")
    await bot.handle_event(event)

    assert "仅限群聊" in sent[0][1].extract_plain_text()


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

    bot, event = _milky_group("ai model set text gpt-4o-mini", user_id=42, role="member")
    await bot.handle_event(event)

    assert len(sent) == 0  # SUPERUSER matcher 直接拦截，非超管无响应
    assert tmp_store.get_scope_model_overrides("milky:123456")["text_model"] == ""


# ------------------------------------------------------- status / stats / clear


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_status_shows_minimal_dashboard(monkeypatch, tmp_store):
    """ai status 只显示当前 provider/文本模型/vision，不暴露代理、渲染等配置细节。"""
    tmp_store.set_scope_provider("milky:123456", "anthropic")
    _, sent, _ = _stub_env(monkeypatch, tmp_store)

    bot, event = _milky_group("ai status")
    await bot.handle_event(event)

    text = sent[0][1].extract_plain_text()
    assert "当前 provider：`anthropic`" in text
    assert "文本模型：`claude-3-5-sonnet`" in text
    assert "vision：`（未设置）`" in text
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
    assert {b["category"]: b["enabled"] for b in bindings} == {"computer": True}


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
    from _helpers import _create_task

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

    # 裸 `ai` 只发送一条状态总览（当前 provider + 文本模型 + vision），不带命令清单。
    assert len(sent) == 1
    text = sent[0][1].extract_plain_text()
    assert "当前 provider" in text
    assert "文本模型" in text
    assert "vision" in text


@pytest.mark.usefixtures("_nonebot_bootstrap")
@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_setup_one_shot_configures_provider(monkeypatch, tmp_store):
    """ai setup：新增 provider + 设默认 + 绑定当前群，一步完成。"""
    _, sent, saved = _stub_env(monkeypatch, tmp_store)

    bot, event = _milky_group("ai setup myllm --url http://x/v1 --key sk-mykey --text deepseek-v3")
    await bot.handle_event(event)

    text = sent[0][1].extract_plain_text()
    assert "已新增 provider `myllm`" in text
    assert "已设为全局默认 provider" in text
    assert "已绑定当前群" in text
    assert "ai vision set" in text  # vision 单独配置提示
    # DB 落库（provider 只有默认文本模型）
    row = tmp_store.get_provider_row("myllm")
    assert row["default_text_model"] == "deepseek-v3"
    assert "default_vision_model" not in row
    assert tmp_store.get_scope_provider("milky:123456") == "myllm"
    assert tmp_store.get_global_value("default_provider") == "myllm"


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_setup_missing_url_key(monkeypatch, tmp_store):
    _, sent, _ = _stub_env(monkeypatch, tmp_store)

    bot, event = _milky_group("ai setup bad --url http://x")
    await bot.handle_event(event)

    assert "需要 --url 与 --key" in sent[0][1].extract_plain_text()
    assert not tmp_store.has_provider_row("bad")


# ------------------------------------------------------- ai config


def _stub_env_file(monkeypatch, tmp_path) -> str:
    """把 ai config 的写盘目标指到临时文件，返回路径。"""
    from hoshino.modules.ai import ai_admin

    env_file = str(tmp_path / "env.prod")
    monkeypatch.setattr(ai_admin, "AI_ENV_FILE", env_file)
    return env_file


@pytest.mark.usefixtures("_nonebot_bootstrap")
@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_config_set_font_writes_env_file(monkeypatch, tmp_store, tmp_path):
    """`ai config set render_font`：写盘 .env.prod，重新加载即生效。"""
    from hoshino.ai.config import load_ai_config_from_env

    env_file = _stub_env_file(monkeypatch, tmp_path)
    _, sent, _ = _stub_env(monkeypatch, tmp_store)

    bot, event = _milky_group("ai config set render_font Noto Sans CJK")
    await bot.handle_event(event)

    text = sent[0][1].extract_plain_text()
    assert "已更新 `render_font`=Noto Sans CJK" in text
    assert "env.prod" in text
    # 写盘内容 + 重新加载生效
    assert "AI_RENDER_FONT=Noto Sans CJK" in open(env_file, encoding="utf-8").read()
    loaded = load_ai_config_from_env(env={}, env_file=env_file)
    assert loaded.render_font == "Noto Sans CJK"


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_config_set_preserves_unrelated_lines(monkeypatch, tmp_store, tmp_path):
    """写盘只改目标行：既有注释与其它配置行原样保留。"""
    env_file = _stub_env_file(monkeypatch, tmp_path)
    with open(env_file, "w", encoding="utf-8") as fh:
        fh.write("# comment\nHOST=0.0.0.0\nAI_RENDER_THEME=dark\n")
    _, sent, _ = _stub_env(monkeypatch, tmp_store)

    bot, event = _milky_group("ai config set render_font Inter")
    await bot.handle_event(event)

    content = open(env_file, encoding="utf-8").read()
    assert "# comment" in content
    assert "HOST=0.0.0.0" in content
    assert "AI_RENDER_THEME=dark" in content
    assert "AI_RENDER_FONT=Inter" in content


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_config_set_rejects_non_render_proxy_keys(monkeypatch, tmp_store, tmp_path):
    """白名单外参数（如历史条数）拒绝修改，不写盘。"""
    env_file = _stub_env_file(monkeypatch, tmp_path)
    _, sent, _ = _stub_env(monkeypatch, tmp_store)

    bot, event = _milky_group("ai config set max_history_messages 10")
    await bot.handle_event(event)

    text = sent[0][1].extract_plain_text()
    assert "仅代理与渲染相关参数可改" in text
    assert not os.path.exists(env_file)


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_config_set_theme_rejects_invalid(monkeypatch, tmp_store, tmp_path):
    """render_theme 只接受 light/dark。"""
    env_file = _stub_env_file(monkeypatch, tmp_path)
    _, sent, _ = _stub_env(monkeypatch, tmp_store)

    bot, event = _milky_group("ai config set render_theme blue")
    await bot.handle_event(event)

    assert "仅支持 light / dark" in sent[0][1].extract_plain_text()
    assert not os.path.exists(env_file)


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_config_set_numeric_validation(monkeypatch, tmp_store, tmp_path):
    """数值参数：非数字与 <=0 拒绝。"""
    env_file = _stub_env_file(monkeypatch, tmp_path)
    _, sent, _ = _stub_env(monkeypatch, tmp_store)

    bot, event = _milky_group("ai config set render_device_scale abc")
    await bot.handle_event(event)
    assert "需要数字" in sent[0][1].extract_plain_text()

    bot, event = _milky_group("ai config set render_timeout_seconds -5")
    await bot.handle_event(event)
    assert "需要大于 0" in sent[1][1].extract_plain_text()
    assert not os.path.exists(env_file)


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_config_set_emoji_normalizes(monkeypatch, tmp_store, tmp_path):
    """render_emoji 接受 1/on 等写法，写盘统一 true/false。"""
    from hoshino.ai.config import load_ai_config_from_env

    env_file = _stub_env_file(monkeypatch, tmp_path)
    _, sent, _ = _stub_env(monkeypatch, tmp_store)

    bot, event = _milky_group("ai config set render_emoji 1")
    await bot.handle_event(event)
    assert "`render_emoji`=true" in sent[0][1].extract_plain_text()
    assert "AI_RENDER_EMOJI=true" in open(env_file, encoding="utf-8").read()
    assert load_ai_config_from_env(env={}, env_file=env_file).render_emoji is True

    bot, event = _milky_group("ai config set render_emoji maybe")
    await bot.handle_event(event)
    assert "仅支持 true / false" in sent[1][1].extract_plain_text()


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_config_proxy_empty_hints_reset(monkeypatch, tmp_store, tmp_path):
    """set proxy 空值提示用 reset 清除。"""
    env_file = _stub_env_file(monkeypatch, tmp_path)
    _, sent, _ = _stub_env(monkeypatch, tmp_store)

    bot, event = _milky_group('ai config set proxy ""')
    await bot.handle_event(event)

    assert "值不能为空" in sent[0][1].extract_plain_text()
    assert "reset proxy" in sent[0][1].extract_plain_text()
    assert not os.path.exists(env_file)


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_config_reset_removes_line(monkeypatch, tmp_store, tmp_path):
    """`ai config reset`：删除对应行恢复默认；白名单外拒绝。"""
    env_file = _stub_env_file(monkeypatch, tmp_path)
    with open(env_file, "w", encoding="utf-8") as fh:
        fh.write("# comment\nAI_RENDER_FONT=Noto Sans\nAI_RENDER_THEME=dark\n")
    _, sent, _ = _stub_env(monkeypatch, tmp_store)

    bot, event = _milky_group("ai config reset render_font")
    await bot.handle_event(event)
    assert "已清除 `render_font`" in sent[0][1].extract_plain_text()
    content = open(env_file, encoding="utf-8").read()
    assert "AI_RENDER_FONT" not in content
    assert "AI_RENDER_THEME=dark" in content  # 其它行保留
    assert "# comment" in content

    bot, event = _milky_group("ai config reset system_prompt")
    await bot.handle_event(event)
    assert "仅代理与渲染相关参数可改" in sent[1][1].extract_plain_text()


async def test_setup_use_proxy_flag(monkeypatch, tmp_store):
    """ai setup --use-proxy：开启/关闭/保持原值。"""
    from hoshino.ai.provider import ProviderRecord, upsert_provider

    upsert_provider(ProviderRecord(id="proxyllm", default_text_model="m", use_proxy=True))

    _, sent, _ = _stub_env(monkeypatch, tmp_store)
    bot, event = _milky_group("ai setup proxyllm --url http://x/v1 --key sk-1 --use-proxy")
    await bot.handle_event(event)
    text = sent[0][1].extract_plain_text()
    assert "全局代理：启用" in text
    assert tmp_store.get_provider_row("proxyllm")["use_proxy"] is True

    bot, event = _milky_group("ai setup proxyllm --url http://x/v1 --key sk-1 --use-proxy 0")
    await bot.handle_event(event)
    assert tmp_store.get_provider_row("proxyllm")["use_proxy"] is False

    # 不带 flag：保持原值
    bot, event = _milky_group("ai setup proxyllm --url http://x/v1 --key sk-1")
    await bot.handle_event(event)
    assert tmp_store.get_provider_row("proxyllm")["use_proxy"] is False
