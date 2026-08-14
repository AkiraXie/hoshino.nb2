"""AI 多模态测试：事件图片 → 内容转换、image_view 工具、chat 双模型选择。

media 与 image_view 的纯逻辑测试不启动 NoneBot；chat 双模型选择走真实
NoneBot dispatch 路径（milky 事件 + stub build_agent/render/send）。
"""

from __future__ import annotations

import itertools
from types import SimpleNamespace

import pytest
from pydantic_ai import BinaryContent, ImageUrl
from pydantic_ai.messages import TextContent

from hoshino.ai.deps import AgentDeps, PermissionSnapshot, Telemetry

pytestmark = pytest.mark.usefixtures("_clear_uninfo_cache")

_seq = itertools.count(500000)


# ------------------------------------------------------------ media 转换


def test_segment_url_becomes_image_url():
    from hoshino.ai.media import image_segments_to_content

    seg = SimpleNamespace(url="https://example.com/a.png", path=None, raw=None)
    parts = image_segments_to_content([seg])
    assert len(parts) == 1
    assert isinstance(parts[0], ImageUrl)
    assert parts[0].url == "https://example.com/a.png"


def test_segment_path_becomes_binary(tmp_path):
    from hoshino.ai.media import image_segments_to_content

    img = tmp_path / "a.png"
    img.write_bytes(b"\x89PNG fake")
    seg = SimpleNamespace(url="", path=str(img), raw=None)
    parts = image_segments_to_content([seg])
    assert len(parts) == 1
    assert isinstance(parts[0], BinaryContent)
    assert parts[0].data == b"\x89PNG fake"
    assert parts[0].media_type == "image/png"


def test_segment_raw_becomes_binary():
    from hoshino.ai.media import image_segments_to_content

    seg = SimpleNamespace(url="", path=None, raw=b"\x89PNG raw")
    parts = image_segments_to_content([seg])
    assert isinstance(parts[0], BinaryContent)
    assert parts[0].data == b"\x89PNG raw"


def test_segment_file_url_becomes_binary(tmp_path):
    from hoshino.ai.media import image_segments_to_content

    img = tmp_path / "a.jpg"
    img.write_bytes(b"jpeg")
    seg = SimpleNamespace(url=f"file://{img}", path=None, raw=None)
    parts = image_segments_to_content([seg])
    assert isinstance(parts[0], BinaryContent)
    assert parts[0].media_type == "image/jpeg"


def test_segment_unresolvable_skipped():
    from hoshino.ai.media import image_segments_to_content

    seg = SimpleNamespace(url="", path=None, raw=None)
    assert image_segments_to_content([seg]) == []


def test_build_multimodal_prompt_falls_back_to_text():
    from hoshino.ai.media import build_multimodal_prompt

    good = SimpleNamespace(url="https://example.com/a.png", path=None, raw=None)
    bad = SimpleNamespace(url="", path=None, raw=None)

    result = build_multimodal_prompt("看图", [good])
    assert isinstance(result, list)
    assert isinstance(result[0], TextContent)
    assert result[0].content == "看图"
    assert isinstance(result[1], ImageUrl)

    # 图片全部解析失败 → 回退纯文本 str
    assert build_multimodal_prompt("看图", [bad]) == "看图"
    assert build_multimodal_prompt("看图", []) == "看图"


# ------------------------------------------------------------ image_view 工具


def _tool_ctx(config=None, provider_id: str = ""):
    from nonebot_plugin_alconna.uniseg import Target

    from hoshino.ai.config import AIConfig

    cfg = config or AIConfig()
    return SimpleNamespace(
        deps=AgentDeps(
            surface="chat",  # type: ignore[arg-type]
            scope_key=None,
            target=Target(id="0", private=True, self_id="10000", adapter="milky"),
            config=cfg,
            permissions=PermissionSnapshot(),
            bot=None,
            event=None,
            telemetry=Telemetry(provider_id=provider_id, scope_key="", model=""),
        )
    )


class _FakeResponse:
    def __init__(
        self, content: bytes = b"", headers: dict | None = None, status: int = 200
    ):
        self.content = content
        self.headers = headers or {}
        self._status = status

    def raise_for_status(self):
        if self._status >= 400:
            import httpx

            request = httpx.Request("GET", "http://fake")
            raise httpx.HTTPStatusError(
                f"http {self._status}",
                request=request,
                response=httpx.Response(self._status, request=request),
            )


class _FakeAsyncClient:
    """替换 httpx.AsyncClient：固定返回预设响应。"""

    def __init__(self, response: _FakeResponse):
        self._response = response

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, url, **kwargs):
        return self._response


def _seed_vision_provider(tmp_store):
    """预置带 vision 模型的 provider 行，返回默认文本模型名。"""
    tmp_store.upsert_provider_row(
        provider_id="openai",
        url="https://api.example.com/v1",
        key="sk-abcdefghij",
        kind="openai_chat",
        default_text_model="gpt-4o-mini",
        default_vision_model="gpt-4o",
    )
    tmp_store.upsert_provider_model("openai", "gpt-4o-mini", "text")
    tmp_store.upsert_provider_model("openai", "gpt-4o", "multimodal")


@pytest.mark.asyncio
async def test_image_view_delegates_to_vision_model(monkeypatch, tmp_store):
    from hoshino.ai.tools.web import image_view as iv

    _seed_vision_provider(tmp_store)
    calls: list = []

    async def fake_describe(record, vision_model, content, *, proxy=None, prompt=None):
        calls.append((record.id, vision_model, content))
        return "图里有一只猫"

    monkeypatch.setattr(iv.vision, "describe_images", fake_describe)
    monkeypatch.setattr(
        iv.httpx,
        "AsyncClient",
        lambda **kw: _FakeAsyncClient(
            _FakeResponse(b"\x89PNG data", {"content-type": "image/png"})
        ),
    )
    out = await iv.image_view(
        _tool_ctx(provider_id="openai"), "https://example.com/a.png"
    )
    assert out == "图里有一只猫"
    assert calls[0][0] == "openai"
    assert calls[0][1] == "gpt-4o"
    content = calls[0][2]
    assert isinstance(content[0], BinaryContent)
    assert content[0].data == b"\x89PNG data"


@pytest.mark.asyncio
async def test_image_view_no_vision_model_reports(monkeypatch, tmp_store):
    from hoshino.ai.tools.web import image_view as iv

    _seed_vision_provider(tmp_store)
    monkeypatch.setattr(
        iv.httpx, "AsyncClient", lambda **kw: _FakeAsyncClient(_FakeResponse(b"x"))
    )
    # 单独一个无 vision 模型的 provider
    tmp_store.upsert_provider_row(
        provider_id="textonly",
        url="https://api.example.com/v1",
        key="sk",
        kind="openai_chat",
        default_text_model="gpt-4o-mini",
    )
    tmp_store.upsert_provider_model("textonly", "gpt-4o-mini", "text")
    out = await iv.image_view(
        _tool_ctx(provider_id="textonly"), "https://example.com/a.png"
    )
    assert "未配置 vision 模型" in out


@pytest.mark.asyncio
async def test_image_view_rejects_private_host(monkeypatch):
    from hoshino.ai.tools.web import image_view as iv

    monkeypatch.setattr(
        iv.httpx, "AsyncClient", lambda **kw: _FakeAsyncClient(_FakeResponse(b"x"))
    )
    out = await iv.image_view(_tool_ctx(), "http://127.0.0.1/secret.png")
    assert "拒绝访问私有" in out


@pytest.mark.asyncio
async def test_image_view_rejects_bad_scheme():
    from hoshino.ai.tools.web import image_view as iv

    out = await iv.image_view(_tool_ctx(), "file:///etc/passwd")
    assert "仅支持 http/https" in out


@pytest.mark.asyncio
async def test_image_view_size_limit(monkeypatch, tmp_store):
    from hoshino.ai.tools.web import image_view as iv

    _seed_vision_provider(tmp_store)
    monkeypatch.setattr(iv.vision, "describe_images", lambda *a, **k: "x")

    async def _noop(*a, **k):
        return "x"

    monkeypatch.setattr(iv.vision, "describe_images", _noop)

    big = b"x" * (15 * 1024 * 1024 + 1)
    monkeypatch.setattr(
        iv.httpx,
        "AsyncClient",
        lambda **kw: _FakeAsyncClient(
            _FakeResponse(big, {"content-type": "image/png"})
        ),
    )
    out = await iv.image_view(
        _tool_ctx(provider_id="openai"), "https://example.com/big.png"
    )
    assert "大小限制" in out


@pytest.mark.asyncio
async def test_image_view_fetch_error(monkeypatch, tmp_store):
    from hoshino.ai.tools.web import image_view as iv

    _seed_vision_provider(tmp_store)

    async def _noop(*a, **k):
        return "x"

    monkeypatch.setattr(iv.vision, "describe_images", _noop)
    monkeypatch.setattr(
        iv.httpx,
        "AsyncClient",
        lambda **kw: _FakeAsyncClient(_FakeResponse(b"", status=404)),
    )
    out = await iv.image_view(
        _tool_ctx(provider_id="openai"), "https://example.com/missing.png"
    )
    assert "抓取失败" in out


# ------------------------------------------------------------ chat 双模型


def _milky_group(
    text: str,
    *,
    user_id: int = 7,
    role: str = "admin",
    group_id: int = 123456,
):
    from nonebot import get_adapters
    from nonebot.adapters.milky import Adapter as MilkyAdapter
    from nonebot.adapters.milky import Bot as MilkyBot
    from nonebot.adapters.milky.config import ClientInfo

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
    event.to_me = False
    return bot, event


def _stub_env(
    monkeypatch, tmp_store, *, vision_model: str = "", render_error: bool = False
):
    """配置 openai provider（可选 vision 默认模型）+ stub render/send。

    ``render_error`` 让渲染抛错（chat 回退纯文本，便于断言 mask 文案）。
    返回 (config, sent)：sent 为 send_group_message 收到的 (group_id, message)。
    """
    from nonebot.adapters.milky import Bot as MilkyBot
    from nonebot.adapters.milky.model.api import MessageResponse

    from hoshino.ai.config import AIConfig
    from hoshino.modules.ai import chat

    tmp_store.upsert_provider_row(
        provider_id="openai",
        url="https://api.example.com/v1",
        key="sk-abcdefghij",
        kind="openai_chat",
        default_text_model="gpt-4o-mini",
        default_vision_model=vision_model,
    )
    tmp_store.upsert_provider_model("openai", "gpt-4o-mini", "text")
    if vision_model:
        tmp_store.upsert_provider_model("openai", vision_model, "multimodal")

    config = AIConfig(default="openai", system_prompt="你是测试助手。")
    monkeypatch.setattr(chat, "get_config", lambda: config)
    monkeypatch.setattr(chat.sv, "check_enabled", lambda scope: True)

    if render_error:

        async def fake_render(md, cfg):
            raise RuntimeError("render boom")

    else:

        async def fake_render(md, cfg):
            return b"FAKEPNG"

    monkeypatch.setattr(chat.rendering, "render_markdown", fake_render)

    sent: list = []

    async def fake_send_group_message(self, *, group_id: int, message):
        sent.append((group_id, message))
        return MessageResponse(message_seq=8, time=1)

    monkeypatch.setattr(MilkyBot, "send_group_message", fake_send_group_message)
    return config, sent


async def _fake_image_segments(bot, event):
    return [SimpleNamespace(url="https://example.com/a.png", path=None, raw=None)]


class _FakeResult:
    def __init__(self, output: str):
        self.output = output
        self._usage = SimpleNamespace(
            requests=1,
            input_tokens=5,
            output_tokens=3,
            cache_read_tokens=0,
            cache_write_tokens=0,
            total_tokens=8,
        )

    def all_messages(self):
        return []

    def usage(self):
        return self._usage


class _FakeAgentRun:
    def __init__(self, result):
        self._result = result
        self.ctx = object()
        self.result = None
        self._count = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._count >= 1:
            self.result = self._result
            raise StopAsyncIteration
        self._count += 1
        return object()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _FakeAgent:
    def __init__(self, result):
        self._result = result

    def iter(self, prompt, **kwargs):
        self.prompt = prompt
        return _FakeAgentRun(self._result)


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_chat_image_with_vision_describes_and_answers_with_text(
    monkeypatch, tmp_store
):
    """含图 + vision 模型：vision 模型描述图片，text 模型作答。"""
    from hoshino.modules.ai import chat

    _, sent = _stub_env(monkeypatch, tmp_store, vision_model="gpt-4o")
    monkeypatch.setattr(chat, "_event_images", _fake_image_segments)

    async def fake_describe(record, vision_model, content, *, proxy=None):
        return "图里有一只猫"

    monkeypatch.setattr(chat.vision, "describe_images", fake_describe)
    captured: dict = {}

    def fake_build(provider_id, record, model, **kwargs):
        captured["model"] = model
        captured["record"] = record
        return _FakeAgent(_FakeResult("看到了"))

    monkeypatch.setattr(chat.providers, "build_agent", fake_build)

    bot, event = _milky_group("#这是什么")
    await bot.handle_event(event)

    assert captured["model"] == "gpt-4o-mini"  # 作答始终用 text 模型
    assert len(sent) == 1
    assert "未配置 vision 模型" not in sent[0][1].extract_plain_text()


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_chat_image_with_vision_injects_description(monkeypatch, tmp_store):
    """vision 模型描述被注入 prompt，text 模型据此作答。"""
    from hoshino.modules.ai import chat

    _stub_env(monkeypatch, tmp_store, vision_model="gpt-4o")
    monkeypatch.setattr(chat, "_event_images", _fake_image_segments)

    async def fake_describe(record, vision_model, content, *, proxy=None):
        return "图里有一只猫"

    monkeypatch.setattr(chat.vision, "describe_images", fake_describe)
    agent = _FakeAgent(_FakeResult("看到了"))
    monkeypatch.setattr(chat.providers, "build_agent", lambda *a, **k: agent)

    bot, event = _milky_group("#这是什么")
    await bot.handle_event(event)

    prompt = agent.prompt
    assert isinstance(prompt, str)
    assert "[图片描述]" in prompt
    assert "图里有一只猫" in prompt
    assert "这是什么" in prompt


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_chat_image_without_vision_uses_text_and_mask(monkeypatch, tmp_store):
    """有图但无 vision 模型：text 模型 + 回复带"未配置 vision 模型"提示。"""
    from hoshino.modules.ai import chat

    _, sent = _stub_env(monkeypatch, tmp_store, render_error=True)  # 回退纯文本
    monkeypatch.setattr(chat, "_event_images", _fake_image_segments)
    captured: dict = {}

    def fake_build(provider_id, record, model, **kwargs):
        captured["model"] = model
        return _FakeAgent(_FakeResult("回答"))

    monkeypatch.setattr(chat.providers, "build_agent", fake_build)

    bot, event = _milky_group("#你好")
    await bot.handle_event(event)

    assert captured["model"] == "gpt-4o-mini"  # text 模型
    assert len(sent) == 1
    assert "未配置 vision 模型" in sent[0][1].extract_plain_text()


@pytest.mark.usefixtures("_nonebot_bootstrap")
async def test_chat_text_without_image_uses_text_model(monkeypatch, tmp_store):
    """无图消息即使配了 vision 模型也走 text 模型。"""
    from hoshino.modules.ai import chat

    _stub_env(monkeypatch, tmp_store, vision_model="gpt-4o")

    async def _no_images(bot, event):
        return []

    monkeypatch.setattr(chat, "_event_images", _no_images)
    captured: dict = {}

    def fake_build(provider_id, record, model, **kwargs):
        captured["model"] = model
        return _FakeAgent(_FakeResult("回答"))

    monkeypatch.setattr(chat.providers, "build_agent", fake_build)

    bot, event = _milky_group("#你好")
    await bot.handle_event(event)

    assert captured["model"] == "gpt-4o-mini"
