"""一次性探针：AI provider 真实代理链路（联网，不进入常规测试）。

运行方式（必须显式开启，避免常规 ``pytest nb-tests`` 触碰网络）：

    ONE_SHOT_LIVE=1 uv run pytest nb-tests/one-shot/test_ai_provider_live.py -s -q

覆盖两件事：
1. 复现"实际 provider 走代理"的端到端探针：本地假代理接收真实
   ``fetch_available_models`` 请求（use_proxy=True 经 OUTSIDE_PROXY 转发、
   False 直连不可达地址）。
2. 对运行时 DB 里真实配置的 provider（data/db/aichat.db 的 ai_providers 表）
   逐个实时拉取可用模型，验证当前 use_proxy/代理解析下真实可达性。
   只打印 provider id / kind / url / use_proxy / 结果，不打印 key。
"""

from __future__ import annotations

import asyncio
import json
import os

import pytest

pytestmark = [
    pytest.mark.skipif(
        not os.environ.get("ONE_SHOT_LIVE"),
        reason="临时联网探针：设置 ONE_SHOT_LIVE=1 才运行",
    ),
    pytest.mark.usefixtures("_nonebot_bootstrap"),
]


class FakeProxy:
    """极简 HTTP 代理：记录请求行，对 GET 返回固定的 /models JSON。"""

    def __init__(self) -> None:
        self.requests: list[str] = []
        self._server: asyncio.AbstractServer | None = None

    @property
    def url(self) -> str:
        assert self._server is not None, "proxy 未启动"
        port = self._server.sockets[0].getsockname()[1]
        return f"http://127.0.0.1:{port}"

    async def start(self) -> None:
        self._server = await asyncio.start_server(self._handle, "127.0.0.1", 0)

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            line = await reader.readline()
            if line:
                self.requests.append(line.decode("latin1").strip())
            while await reader.readline() not in (b"\r\n", b"\n"):
                pass
            body = json.dumps({"data": [{"id": "model-b"}, {"id": "model-a"}]}).encode()
            writer.write(
                b"HTTP/1.1 200 OK\r\n"
                b"Content-Type: application/json\r\n"
                + f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n".encode()
                + body
            )
            await writer.drain()
        finally:
            writer.close()

    async def stop(self) -> None:
        if self._server:
            self._server.close()
            await self._server.wait_closed()


@pytest.fixture
async def fake_proxy():
    proxy = FakeProxy()
    await proxy.start()
    yield proxy
    await proxy.stop()


def _record(use_proxy: bool) -> object:
    from hoshino.ai.provider import ProviderRecord

    # TEST-NET-1（192.0.2.0/24）：公网不可达，只有经代理转发才能拿到响应。
    return ProviderRecord(
        id="probe",
        url="http://192.0.2.1",
        key="sk-probe",
        kind="openai_chat",
        use_proxy=use_proxy,
        timeout_seconds=5.0,
    )


async def test_use_proxy_true_routes_through_outside_proxy(monkeypatch, fake_proxy):
    """use_proxy=True：真实 fetch_available_models 必须经 OUTSIDE_PROXY 转发。"""
    monkeypatch.setenv("OUTSIDE_PROXY", fake_proxy.url)
    from hoshino.ai import provider

    record = _record(use_proxy=True)
    effective = provider.resolve_effective_proxy(record, None)
    assert effective == fake_proxy.url
    models = await provider.fetch_available_models(record, proxy=effective, verify=True)
    assert models == ["model-a", "model-b"]
    assert fake_proxy.requests and "/models" in fake_proxy.requests[0]


async def test_use_proxy_true_falls_back_to_config_proxy(monkeypatch, fake_proxy):
    """use_proxy=True 但未设 OUTSIDE_PROXY：回退 AI 配置代理。"""
    monkeypatch.delenv("OUTSIDE_PROXY", raising=False)
    from hoshino.ai import provider

    record = _record(use_proxy=True)
    effective = provider.resolve_effective_proxy(record, fake_proxy.url)
    assert effective == fake_proxy.url
    models = await provider.fetch_available_models(record, proxy=effective, verify=True)
    assert models == ["model-a", "model-b"]


async def test_use_proxy_false_goes_direct(monkeypatch, fake_proxy):
    """use_proxy=False：直连不可达地址返回 None，且代理侧收不到任何请求。"""
    monkeypatch.setenv("OUTSIDE_PROXY", fake_proxy.url)
    from hoshino.ai import provider

    record = _record(use_proxy=False)
    assert provider.resolve_effective_proxy(record, None) is None
    models = await provider.fetch_available_models(record, proxy=None, verify=True)
    assert models is None
    assert fake_proxy.requests == []


async def test_real_db_providers_live():
    """对真实配置的 provider 逐个实时拉模型（代理按当前解析逻辑生效）。"""
    from hoshino.ai import provider, store
    from hoshino.ai.config import AIConfig

    rows = store.list_provider_rows() or []
    print(f"\n真实 DB 共 {len(rows)} 个 provider：")
    for row in rows:
        record = provider.ProviderRecord.from_row(row)
        effective = provider.resolve_effective_proxy(record, AIConfig().proxy)
        try:
            models = await provider.fetch_available_models(
                record, proxy=effective, verify=True, timeout=20.0
            )
            status = f"ok, {len(models)} models" if models else "无模型/失败"
        except Exception as exc:
            status = f"异常: {type(exc).__name__}"
        print(
            f"  [{record.id}] kind={record.kind} use_proxy={record.use_proxy} "
            f"proxy={effective or '直连'} -> {status}"
        )
        print(f"      url={record.url}")
    assert rows, "真实 DB 没有 provider（aichat.db 未配置？）"
