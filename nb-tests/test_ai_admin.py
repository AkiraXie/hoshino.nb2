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
    _, sent, saved = _stub_env(monkeypatch, tmp_store, superuser=False)

    bot, event = _milky_group("ai provider default anthropic")
    await bot.handle_event(event)

    assert saved == []
    assert len(sent) == 1
    assert "仅 SUPERUSER" in sent[0][1].extract_plain_text()


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
    # role=member 且非 SUPERUSER → 不满足 ADMIN permission → matcher 不执行
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

    bot, event = _milky_group("ai provider add ghost --url http://x --key k")
    await bot.handle_event(event)

    assert saved == []
    assert "仅 SUPERUSER" in sent[0][1].extract_plain_text()


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_provider_add_success(monkeypatch, tmp_store):
    _, sent, saved = _stub_env(monkeypatch, tmp_store, superuser=True)

    bot, event = _milky_group(
        "ai provider add myllm --url http://x/v1 --key sk-mykey "
        "--kind openai_chat --model llama-3 --temperature 0.5 --max-tokens 512"
    )
    await bot.handle_event(event)

    assert saved == []  # provider 写 DB，不再写 service_config
    row = tmp_store.get_provider_row("myllm")
    assert row["url"] == "http://x/v1"
    assert row["key"] == "sk-mykey"
    assert row["kind"] == "openai_chat"
    assert row["default_text_model"] == "llama-3"
    assert row["default_vision_model"] == ""
    assert row["temperature"] == 0.5
    assert row["max_tokens"] == 512
    # 默认模型自动注册进 model-list
    assert tmp_store.get_provider_model("myllm", "llama-3")["capabilities"] == "text"
    assert "已新增 provider" in sent[0][1].extract_plain_text()
    assert not tmp_store.has_provider_row("ghost")  # 无关 provider 不受影响


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_provider_add_registers_vision_model(monkeypatch, tmp_store):
    _, sent, _ = _stub_env(monkeypatch, tmp_store, superuser=True)

    bot, event = _milky_group(
        "ai provider add multi --url http://x --key k --model t --vision-model v"
    )
    await bot.handle_event(event)

    row = tmp_store.get_provider_row("multi")
    assert row["default_text_model"] == "t"
    assert row["default_vision_model"] == "v"
    assert tmp_store.get_provider_model("multi", "t")["capabilities"] == "text"
    assert tmp_store.get_provider_model("multi", "v")["capabilities"] == "multimodal"
    assert "已新增 provider" in sent[0][1].extract_plain_text()


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_provider_add_invalid_kind(monkeypatch, tmp_store):
    _, sent, saved = _stub_env(monkeypatch, tmp_store)

    bot, event = _milky_group("ai provider add bad --kind nonsense --url u --key k")
    await bot.handle_event(event)

    assert saved == []
    assert "kind 必须是" in sent[0][1].extract_plain_text()
    assert not tmp_store.has_provider_row("bad")


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_provider_remove_default_rejected(monkeypatch, tmp_store):
    _, sent, saved = _stub_env(monkeypatch, tmp_store)

    bot, event = _milky_group("ai provider remove openai")
    await bot.handle_event(event)

    assert saved == []
    assert "默认 provider" in sent[0][1].extract_plain_text()


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_provider_remove_success_cleans_refs(monkeypatch, tmp_store):
    tmp_store.set_scope_provider("milky:123456", "anthropic")
    tmp_store.upsert_provider_model("anthropic", "claude-3-5-sonnet", "text")
    _, sent, saved = _stub_env(monkeypatch, tmp_store)

    bot, event = _milky_group("ai provider remove anthropic")
    await bot.handle_event(event)

    assert saved == []
    assert tmp_store.get_provider_row("anthropic") is None
    assert tmp_store.list_provider_models("anthropic") == []  # model-list 一并删除
    assert tmp_store.get_scope_provider("milky:123456") is None  # 引用已清理
    assert "已删除" in sent[0][1].extract_plain_text()


# ------------------------------------------------------- model-list 命令


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_provider_model_list_shows_models(monkeypatch, tmp_store):
    tmp_store.upsert_provider_model("openai", "gpt-4o", "both")
    tmp_store.upsert_provider_model("openai", "gpt-4o-mini", "text")
    _, sent, _ = _stub_env(monkeypatch, tmp_store)

    bot, event = _milky_group("ai provider model-list openai")
    await bot.handle_event(event)

    text = sent[0][1].extract_plain_text()
    assert "gpt-4o-mini" in text and "[text]" in text
    assert "gpt-4o" in text and "[both]" in text


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_provider_model_list_unknown_provider(monkeypatch, tmp_store):
    _, sent, _ = _stub_env(monkeypatch, tmp_store)

    bot, event = _milky_group("ai provider model-list ghost")
    await bot.handle_event(event)

    assert "不存在" in sent[0][1].extract_plain_text()


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_provider_model_add_requires_superuser(monkeypatch, tmp_store):
    _, sent, _ = _stub_env(monkeypatch, tmp_store, superuser=False)

    bot, event = _milky_group("ai provider model-add openai new-model")
    await bot.handle_event(event)

    assert "仅 SUPERUSER" in sent[0][1].extract_plain_text()
    assert tmp_store.get_provider_model("openai", "new-model") is None


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_provider_model_add_success(monkeypatch, tmp_store):
    _, sent, _ = _stub_env(monkeypatch, tmp_store, superuser=True)

    bot, event = _milky_group("ai provider model-add openai gpt-4o --capabilities both")
    await bot.handle_event(event)

    entry = tmp_store.get_provider_model("openai", "gpt-4o")
    assert entry["capabilities"] == "both"
    assert "已注册模型" in sent[0][1].extract_plain_text()


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_provider_model_add_invalid_capabilities(monkeypatch, tmp_store):
    _, sent, _ = _stub_env(monkeypatch, tmp_store, superuser=True)

    bot, event = _milky_group("ai provider model-add openai m --capabilities nope")
    await bot.handle_event(event)

    assert "capabilities 必须是" in sent[0][1].extract_plain_text()
    assert tmp_store.get_provider_model("openai", "m") is None


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_provider_model_remove_default_rejected(monkeypatch, tmp_store):
    _, sent, _ = _stub_env(monkeypatch, tmp_store, superuser=True)

    bot, event = _milky_group("ai provider model-remove openai gpt-4o-mini")
    await bot.handle_event(event)

    assert "默认模型" in sent[0][1].extract_plain_text()
    assert tmp_store.get_provider_model("openai", "gpt-4o-mini") is not None


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_provider_model_remove_success(monkeypatch, tmp_store):
    tmp_store.upsert_provider_model("openai", "extra", "text")
    _, sent, _ = _stub_env(monkeypatch, tmp_store, superuser=True)

    bot, event = _milky_group("ai provider model-remove openai extra")
    await bot.handle_event(event)

    assert tmp_store.get_provider_model("openai", "extra") is None
    assert "已从" in sent[0][1].extract_plain_text()


# ------------------------------------------------------- scope 模型命令


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_model_show_inherits_provider_defaults(monkeypatch, tmp_store):
    _, sent, _ = _stub_env(monkeypatch, tmp_store)

    bot, event = _milky_group("ai model show")
    await bot.handle_event(event)

    text = sent[0][1].extract_plain_text()
    assert "gpt-4o-mini" in text  # openai 默认文本模型
    assert "（无）" in text  # vision 默认空


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_model_set_text_validates_model_list(monkeypatch, tmp_store):
    _, sent, _ = _stub_env(monkeypatch, tmp_store)

    bot, event = _milky_group("ai model set text not-in-list")
    await bot.handle_event(event)

    assert "不在" in sent[0][1].extract_plain_text()
    assert tmp_store.get_scope_model_overrides("milky:123456") == {
        "text_model": "",
        "vision_model": "",
    }


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_model_set_vision_rejects_text_only_model(monkeypatch, tmp_store):
    _, sent, _ = _stub_env(monkeypatch, tmp_store)

    bot, event = _milky_group("ai model set vision gpt-4o-mini")
    await bot.handle_event(event)

    text = sent[0][1].extract_plain_text()
    assert "不能用作多模态模型" in text
    assert tmp_store.get_scope_model_overrides("milky:123456")["vision_model"] == ""


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_model_set_success_and_reset(monkeypatch, tmp_store):
    tmp_store.upsert_provider_model("openai", "gpt-4o", "both")
    _, sent, _ = _stub_env(monkeypatch, tmp_store)

    bot, event = _milky_group("ai model set text gpt-4o")
    await bot.handle_event(event)
    assert "已设为" in sent[0][1].extract_plain_text()
    assert tmp_store.get_scope_model_overrides("milky:123456")["text_model"] == "gpt-4o"

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
    # role=member 且非 SUPERUSER → 不满足 ADMIN permission → matcher 不执行
    _, sent, _ = _stub_env(monkeypatch, tmp_store, superuser=False)

    bot, event = _milky_group(
        "ai model set text gpt-4o-mini", user_id=42, role="member"
    )
    await bot.handle_event(event)

    assert len(sent) == 0  # ADMIN matcher 直接拦截，成员无响应
    assert tmp_store.get_scope_model_overrides("milky:123456")["text_model"] == ""


# ------------------------------------------------------- status / stats / clear


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_status_shows_config(monkeypatch, tmp_store):
    tmp_store.set_scope_provider("milky:123456", "anthropic")
    _, sent, _ = _stub_env(monkeypatch, tmp_store)

    bot, event = _milky_group("ai status")
    await bot.handle_event(event)

    text = sent[0][1].extract_plain_text()
    assert "openai" in text
    assert "anthropic" in text
    assert "64 条" in text
    assert "30.0" in text


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

    assert "仅超管" in sent[0][1].extract_plain_text()
    assert tmp_store.list_scope_tool_bindings("milky:123456", "chat") == []


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_persona_create_use_flow(monkeypatch, tmp_store):
    _, sent, _ = _stub_env(monkeypatch, tmp_store)

    bot, event = _milky_group(
        "ai persona create 小爱 --gender 女性 --personality 温柔 --description 测试人格"
    )
    await bot.handle_event(event)

    text = sent[0][1].extract_plain_text()
    assert "已创建 persona `小爱`" in text
    assert "温柔" in text
    assert tmp_store.get_persona_by_name("小爱") is not None

    bot, event = _milky_group("ai persona use 小爱")
    await bot.handle_event(event)

    assert "已绑定" in sent[-1][1].extract_plain_text()
    assert tmp_store.get_scope_persona_id("milky:123456") is not None


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_persona_create_duplicate_rejected(monkeypatch, tmp_store):
    """重名创建走提示而不是抛 IntegrityError 崩 matcher（原 persona 不被覆盖）。"""
    _, sent, _ = _stub_env(monkeypatch, tmp_store)

    bot, event = _milky_group(
        "ai persona create 小爱 --gender 女性 --personality 温柔 --description 原版"
    )
    await bot.handle_event(event)
    assert "已创建" in sent[0][1].extract_plain_text()

    bot, event = _milky_group(
        "ai persona create 小爱 --gender 女性 --personality 急躁 --description 覆盖"
    )
    await bot.handle_event(event)
    assert "已存在" in sent[-1][1].extract_plain_text()
    assert tmp_store.get_persona_by_name("小爱")["description"] == "原版"


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

    assert "仅 SUPERUSER" in sent[0][1].extract_plain_text()
    assert tmp_store.get_global_value("global_persona") is None


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_task_workspaces_root_hidden_from_member(monkeypatch, tmp_store):
    """workspace 本机绝对路径只对 ADMIN+ 展示，普通成员只见名称/模式（plan 8.1）。"""
    from hoshino.ai.task import store as task_store

    _, sent, _ = _stub_env(monkeypatch, tmp_store, superuser=False)
    task_store.add_workspace("milky:123456", "proj", "/srv/secret/proj", "read_write")

    bot, event = _milky_group("ai task workspaces", role="member", user_id=43)
    await bot.handle_event(event)
    assert "/srv/secret/proj" not in sent[-1][1].extract_plain_text()

    bot, event = _milky_group("ai task workspaces", role="admin")
    await bot.handle_event(event)
    assert "/srv/secret/proj" in sent[-1][1].extract_plain_text()


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_task_list_visibility_matrix(monkeypatch, tmp_store):
    """list 权限矩阵（plan 5.1）：创建者看自己；ADMIN 看本 scope；SUPERUSER 看全部。"""
    from test_ai_task import _create_task

    _, sent, _ = _stub_env(monkeypatch, tmp_store, superuser=False)
    # 用户 43 与另一用户 7 各一个 Task，同 scope
    _create_task(tmp_store, task_id="t_mine", creator_id="43")
    _create_task(tmp_store, task_id="t_other", creator_id="7")

    # 普通成员：只见自己创建的（user_id=43 避免与 admin 分发共用 uninfo 会话缓存）
    bot, event = _milky_group("ai task list", role="member", user_id=43)
    await bot.handle_event(event)
    text = sent[-1][1].extract_plain_text()
    assert "t_mine" in text
    assert "t_other" not in text

    # ADMIN：见本 scope 全部
    bot, event = _milky_group("ai task list", role="admin")
    await bot.handle_event(event)
    text = sent[-1][1].extract_plain_text()
    assert "t_mine" in text
    assert "t_other" in text
