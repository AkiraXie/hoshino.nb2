"""zssm（这是什么）插件测试：文本/回复/链接/图片/权限与错误路径。"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from nonebot.adapters.milky import Bot as MilkyBot
from nonebot.adapters.milky.config import ClientInfo
from nonebot.adapters.milky.event import GroupMessageEvent as MilkyGroupMessageEvent
from nonebot.adapters.milky.model.api import MessageResponse
from pydantic_ai.messages import ModelResponse, TextPart

from conftest import next_seq
from hoshino.ai.config import AIConfig

pytestmark = pytest.mark.usefixtures("_clear_uninfo_cache")


@pytest.fixture(autouse=True)
def _fresh_model_cache(monkeypatch):
    """每个测试独立解释 model 缓存：模块级缓存会跨测试残留旧 fake。"""
    from hoshino.modules.ai import zssm

    monkeypatch.setattr(zssm, "_model_cache", {})


_DEFAULT_MODEL_TEXT = '{"output":"这是一张显卡","keywords":["显卡"],"blocked":false}'


def _milky_group(
    text: str,
    *,
    user_id: int = 42,
    role: str = "member",
    group_id: int = 123456,
    reply: dict | None = None,
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
            **({"reply": reply} if reply is not None else {}),
        }
    )
    assert isinstance(event, MilkyGroupMessageEvent)
    event.to_me = False
    return bot, event


def _milky_reply(sender_id: int, text: str, seq: int = 77) -> dict:
    """构造 Milky 引用消息对象（IncomingMessage 字典）。"""
    return {
        "message_scene": "group",
        "peer_id": 123456,
        "message_seq": seq,
        "sender_id": sender_id,
        "time": 1,
        "segments": [{"type": "text", "data": {"text": text}}],
    }


class FakeModel:
    """Model.request 替身：记录收到的 messages，返回预设 JSON 文本。"""

    def __init__(self, text: str = _DEFAULT_MODEL_TEXT):
        self._text = text
        self.messages: list | None = None

    async def request(self, messages, model_settings, model_request_parameters):
        self.messages = messages
        return ModelResponse(parts=[TextPart(content=self._text)])


def _stub_env(
    monkeypatch,
    tmp_store,
    *,
    model_text: str = _DEFAULT_MODEL_TEXT,
    with_vision: bool = False,
):
    """stub zssm 的 config / store / build_model / 发送，返回 (fake_model, sent)。

    ``with_vision`` 时写全局默认 vision（``ai vision default`` 的 KV），
    zssm 经 ``provider.resolve_vision`` 走全局回退。
    """
    from hoshino.modules.ai import zssm

    monkeypatch.setattr(zssm.sv, "check_enabled", lambda scope: True)
    config = AIConfig(default="openai")
    monkeypatch.setattr(zssm, "get_config", lambda: config)

    tmp_store.upsert_provider_row(
        provider_id="openai",
        url="https://api.example.com/v1",
        key="sk-abcdefghij",
        kind="openai_chat",
        default_text_model="gpt-4o-mini",
    )
    tmp_store.upsert_provider_model("openai", "gpt-4o-mini", "text")
    if with_vision:
        tmp_store.set_global_value("default_vision_provider", "openai")
        tmp_store.set_global_value("default_vision_model", "gpt-4o")

    fake = FakeModel(model_text)
    monkeypatch.setattr(zssm.providers, "build_model", lambda *a, **k: fake)

    sent: list[tuple[int, object]] = []

    async def fake_send_group_message(self, *, group_id: int, message):
        sent.append((group_id, message))
        return MessageResponse(message_seq=8, time=1)

    monkeypatch.setattr(MilkyBot, "send_group_message", fake_send_group_message)
    return fake, sent


def _user_payload(fake_model) -> dict:
    """取出 fake 收到的 user prompt 文本（JSON 解码；vision 时取 TextContent）。"""
    request = fake_model.messages[0]
    part = request.parts[-1]
    content = part.content
    if isinstance(content, list):
        content = next(item.content for item in content if type(item).__name__ == "TextContent")
    return json.loads(content)


# ------------------------------------------------------- 文本


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_zssm_direct_text_explains(monkeypatch, tmp_store):
    """`zssm <text>`：target 为命令参数，普通成员可用，回复解析后的解释。"""
    fake, sent = _stub_env(monkeypatch, tmp_store)

    bot, event = _milky_group("zssm hello world --text")
    await bot.handle_event(event)

    payload = _user_payload(fake)
    assert payload["target"] == "hello world"
    assert payload["focus"] == ""
    assert payload["resources"] == []
    text = sent[0][1].extract_plain_text()
    assert "关键词：显卡" in text
    assert "这是一张显卡" in text


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_zssm_reply_target_and_focus(monkeypatch, tmp_store):
    """回复某条消息 + `zssm <focus>`：target 是回复内容，focus 是命令参数。"""
    fake, sent = _stub_env(monkeypatch, tmp_store)

    bot, event = _milky_group("zssm 显卡 --text", reply=_milky_reply(7, "RTX 4090 好贵啊"))
    await bot.handle_event(event)

    payload = _user_payload(fake)
    assert payload["target"] == "RTX 4090 好贵啊"
    assert payload["focus"] == "显卡"
    assert "关键词：显卡" in sent[0][1].extract_plain_text()


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_zssm_empty_target_shows_usage(monkeypatch, tmp_store):
    """`zssm` 无参数且无回复：用法提示，不请求模型。"""
    fake, sent = _stub_env(monkeypatch, tmp_store)

    bot, event = _milky_group("zssm")
    await bot.handle_event(event)

    assert "用法：zssm" in sent[0][1].extract_plain_text()
    assert fake.messages is None  # 未调用模型


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_zssm_without_provider_shows_error(monkeypatch, tmp_store):
    """无可用 provider：提示联系管理员，不请求模型。"""
    fake, sent = _stub_env(monkeypatch, tmp_store)
    tmp_store.delete_provider_row("openai")

    bot, event = _milky_group("zssm 随便什么")
    await bot.handle_event(event)

    assert "AI 服务未配置任何 provider" in sent[0][1].extract_plain_text()
    assert fake.messages is None


# ------------------------------------------------------- 链接


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_zssm_fetches_links(monkeypatch, tmp_store):
    """target 中的链接被抓取进 resources（失败不阻断）。"""
    from hoshino.modules.ai import zssm

    fake, sent = _stub_env(monkeypatch, tmp_store)

    async def fake_fetch(url, *, verify_ssl=False, proxy=None):
        return f"[{url} 的正文]"

    monkeypatch.setattr(zssm.link, "fetch_url_to_markdown", fake_fetch)

    bot, event = _milky_group("zssm 看看 https://example.com/page 是什么 --text")
    await bot.handle_event(event)

    payload = _user_payload(fake)
    assert payload["resources"][0]["url"] == "https://example.com/page"
    assert payload["resources"][0]["kind"] == "web"
    assert payload["resources"][0]["content"] == "[https://example.com/page 的正文]"
    assert "关键词：显卡" in sent[0][1].extract_plain_text()


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_zssm_link_web_fail_falls_back_to_browser(monkeypatch, tmp_store):
    """web_fetch 失败时回退 browser_use 渲染截图描述（kind=browser）。"""
    from hoshino.modules.ai import zssm

    fake, sent = _stub_env(monkeypatch, tmp_store, with_vision=True)

    async def fail_fetch(url, *, verify_ssl=False, proxy=None):
        return "抓取失败（ConnectError）。"

    monkeypatch.setattr(zssm.link, "fetch_url_to_markdown", fail_fetch)

    async def fake_browse(
        url, *, proxy=None, fetch_proxy=None, record=None, vision_model="", prompt=""
    ):
        return "页面渲染后的内容描述"

    monkeypatch.setattr(zssm.link, "browse_page_description", fake_browse)

    bot, event = _milky_group("zssm https://example.com/x --text")
    await bot.handle_event(event)

    payload = _user_payload(fake)
    assert payload["resources"][0]["kind"] == "browser"
    assert payload["resources"][0]["content"] == "页面渲染后的内容描述"
    assert "关键词：显卡" in sent[0][1].extract_plain_text()


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_zssm_link_both_fail_report_error(monkeypatch, tmp_store):
    """web_fetch 与 browser_use 都失败：直接报错，不再继续解释。"""
    from hoshino.modules.ai import zssm

    fake, sent = _stub_env(monkeypatch, tmp_store, with_vision=True)

    async def fail_fetch(url, *, verify_ssl=False, proxy=None):
        return "抓取失败（ConnectError）。"

    monkeypatch.setattr(zssm.link, "fetch_url_to_markdown", fail_fetch)

    async def fail_browse(
        url, *, proxy=None, fetch_proxy=None, record=None, vision_model="", prompt=""
    ):
        return "网页加载超时。"

    monkeypatch.setattr(zssm.link, "browse_page_description", fail_browse)

    bot, event = _milky_group("zssm https://example.com/x --text")
    await bot.handle_event(event)

    assert "无法获取页面内容" in sent[0][1].extract_plain_text()
    assert fake.messages is None  # 未请求模型


# ------------------------------------------------------- 图片（原图直传）


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_zssm_image_with_vision_describes(monkeypatch, tmp_store):
    """有 vision 模型时图片先描述再解释，描述注入 prompt。"""
    from hoshino.modules.ai import zssm

    fake, sent = _stub_env(monkeypatch, tmp_store, with_vision=True)

    async def fake_images(bot, event):
        return [SimpleNamespace(url="https://x/a.png")]

    monkeypatch.setattr(zssm.image, "event_images", fake_images)

    async def fake_describe_url(
        url, *, verify_ssl=False, proxy=None, fetch_proxy=None, record=None, vision_model=""
    ):
        return "图片里有一张显卡"

    monkeypatch.setattr(zssm.image, "describe_image_url", fake_describe_url)

    bot, event = _milky_group("zssm 这图是啥 --text")
    await bot.handle_event(event)

    payload = _user_payload(fake)
    # 描述按图片序号分块（对齐 djkcyl 的占位符-描述对应）
    assert payload["image_descriptions"] == "图片1：图片里有一张显卡"
    assert "关键词：显卡" in sent[0][1].extract_plain_text()


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_zssm_image_without_vision_hints(monkeypatch, tmp_store):
    """纯图片场景无 vision 模型：提示无法识别，不请求模型。"""
    from hoshino.modules.ai import zssm

    fake, sent = _stub_env(monkeypatch, tmp_store, with_vision=False)

    async def fake_images(bot, event):
        return [SimpleNamespace(url="https://x/a.png")]

    monkeypatch.setattr(zssm.image, "event_images", fake_images)

    bot, event = _milky_group("zssm --text")
    await bot.handle_event(event)

    assert "无法识别图片内容" in sent[0][1].extract_plain_text()
    assert fake.messages is None


# ------------------------------------------------------- 输出与渲染


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_zssm_default_renders_markdown_image(monkeypatch, tmp_store):
    """默认把解释 Markdown 渲染为图片回复。"""
    from hoshino.modules.ai import zssm

    fake, sent = _stub_env(monkeypatch, tmp_store)

    async def fake_render(md, cfg):
        return b"FAKEPNG"

    monkeypatch.setattr(zssm.rendering, "render_markdown", fake_render)

    bot, event = _milky_group("zssm hello")
    await bot.handle_event(event)

    assert len(sent) == 1
    group_id, message = sent[0]
    assert [segment.type for segment in message] == ["image"]
    # Milky 导出时 raw bytes 转 base64 uri
    assert message[0].data["uri"].startswith("base64://")


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_zssm_render_failure_falls_back_to_text(monkeypatch, tmp_store):
    """渲染失败回退纯文本。"""
    from hoshino.modules.ai import zssm

    fake, sent = _stub_env(monkeypatch, tmp_store)

    async def broken_render(md, cfg):
        raise RuntimeError("no browser")

    monkeypatch.setattr(zssm.rendering, "render_markdown", broken_render)

    bot, event = _milky_group("zssm hello")
    await bot.handle_event(event)

    group_id, message = sent[0]
    assert [segment.type for segment in message] == ["text"]
    assert "关键词：显卡" in message.extract_plain_text()


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_zssm_text_flag_skips_render(monkeypatch, tmp_store):
    """`--text` 直接纯文本回复，不渲染图片。"""
    from hoshino.modules.ai import zssm

    fake, sent = _stub_env(monkeypatch, tmp_store)

    async def unexpected_render(md, cfg):
        raise AssertionError("--text 不应触发渲染")

    monkeypatch.setattr(zssm.rendering, "render_markdown", unexpected_render)

    bot, event = _milky_group("zssm hello --text")
    await bot.handle_event(event)

    payload = _user_payload(fake)
    assert payload["target"] == "hello"  # --text 从参数中剥离
    group_id, message = sent[0]
    assert [segment.type for segment in message] == ["text"]


# ------------------------------------------------------- 单次发送


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_zssm_reply_to_bot_message_sends_once(monkeypatch, tmp_store):
    """回复 bot 自己的消息 + zssm：只发送一条（block 阻止 aichat 重复响应）。"""
    from hoshino.modules.ai import chat

    fake, sent = _stub_env(monkeypatch, tmp_store)
    # 同时开启 aichat（enable_on_default=False，测试里显式开启）：
    # 若 zssm matcher 不 block，aichat 的回复触发也会响应 → 两条。
    monkeypatch.setattr(chat.sv, "check_enabled", lambda scope: True)

    bot, event = _milky_group(
        "zssm 这是什么 --text", reply=_milky_reply(10000, "bot 发的上一条消息")
    )
    await bot.handle_event(event)

    assert len(sent) == 1  # 只有 zssm 一条解释
    assert "关键词：显卡" in sent[0][1].extract_plain_text()


# ------------------------------------------------------- 输出解析


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_zssm_blocked_response(monkeypatch, tmp_store):
    """blocked=true：返回“还不会”而不是原样 JSON。"""
    fake, sent = _stub_env(
        monkeypatch, tmp_store, model_text='{"output":"","keywords":[],"blocked":true}'
    )

    bot, event = _milky_group("zssm 神秘代码 --text")
    await bot.handle_event(event)

    assert "（抱歉，我现在还不会这个）" in sent[0][1].extract_plain_text()


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_zssm_malformed_json_keeps_raw(monkeypatch, tmp_store):
    """模型返回非 JSON：保留原文回复。"""
    fake, sent = _stub_env(monkeypatch, tmp_store, model_text="不解释了")

    bot, event = _milky_group("zssm hello --text")
    await bot.handle_event(event)

    assert "不解释了" in sent[0][1].extract_plain_text()
