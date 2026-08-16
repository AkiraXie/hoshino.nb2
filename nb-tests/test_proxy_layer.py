"""aiohttpx 代理分层：默认直连（不读系统代理），显式 proxy 才走代理。

解析模块（douyin/weibo/xiaohongshu/bilibili 等）全部经 aiohttpx 请求，必须
保持直连；境外服务（steam/x/telegram）统一从 ``OUTSIDE_PROXY`` 环境变量取
代理。本文件验证两层互不干扰与全局代理配置的读取。
"""

from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import ClassVar

import pytest

from hoshino.util import aiohttpx
from hoshino.util.proxy import (
    OUTSIDE_PROXY_ENV,
    apply_telegram_proxy,
    get_outside_proxy,
    normalize_proxy,
)


class _TargetHandler(BaseHTTPRequestHandler):
    """本地目标服务器：记录请求路径，返回 ``direct``。"""

    protocol_version = "HTTP/1.1"
    seen: ClassVar[list[str]] = []

    def do_GET(self):
        self.seen.append(self.path)
        body = b"direct"
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args: object) -> None:
        pass


class _ProxyHandler(BaseHTTPRequestHandler):
    """本地 HTTP 代理：记录绝对 URL 请求并直接返回 ``proxied``。

    不做真实转发：代理请求的 ``self.path`` 是绝对 URL（如
    ``http://example.invalid/hello``），据此断言流量确实经过了代理。
    """

    protocol_version = "HTTP/1.1"
    seen: ClassVar[list[str]] = []

    def do_GET(self):
        self.seen.append(self.path)
        body = b"proxied"
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args: object) -> None:
        pass


def _serve(handler_cls: type[BaseHTTPRequestHandler]) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler_cls)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


@pytest.fixture
def target_server():
    _TargetHandler.seen = []
    server = _serve(_TargetHandler)
    yield server
    server.shutdown()
    server.server_close()


@pytest.fixture
def proxy_server():
    _ProxyHandler.seen = []
    server = _serve(_ProxyHandler)
    yield server
    server.shutdown()
    server.server_close()


@pytest.fixture
async def httpx_clients():
    """初始化并关闭 aiohttpx 共享客户端（生产环境由 startup/shutdown hook 管理）。"""
    await aiohttpx.init_httpx_client()
    yield
    await aiohttpx.close_httpx_client()


async def test_direct_request_ignores_system_proxy(monkeypatch, target_server, httpx_clients):
    """系统代理指向不可达端口时，默认请求仍直连成功（trust_env=False）。"""
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:1")
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:1")
    monkeypatch.setenv("ALL_PROXY", "http://127.0.0.1:1")
    monkeypatch.setenv("NO_PROXY", "")  # 清空豁免，保证若读代理必然走假代理

    url = f"http://127.0.0.1:{target_server.server_port}/ping"
    response = await aiohttpx.get(url, timeout=5)
    assert response.status_code == 200
    assert response.content == b"direct"
    assert _TargetHandler.seen == ["/ping"]


async def test_explicit_proxy_routes_through_proxy(proxy_server, httpx_clients):
    """显式传入 proxy 时请求经过代理（代理收到绝对 URL 请求）。"""
    url = "http://example.invalid/hello"  # 直连必失败，只有经代理才能拿到响应
    proxy = f"http://127.0.0.1:{proxy_server.server_port}"
    response = await aiohttpx.get(url, timeout=5, proxy=proxy)
    assert response.status_code == 200
    assert response.content == b"proxied"
    assert _ProxyHandler.seen == ["http://example.invalid/hello"]


async def test_proxy_clients_cached_and_separate(httpx_clients):
    """相同 proxy 复用同一客户端；直连与代理客户端分离且均不读系统代理。"""
    direct = await aiohttpx.get_client()
    proxied = await aiohttpx.get_client(proxy="http://127.0.0.1:8080")
    proxied_again = await aiohttpx.get_client(proxy="http://127.0.0.1:8080")
    assert proxied is proxied_again
    assert direct is not proxied
    assert direct.trust_env is False
    assert proxied.trust_env is False


async def test_proxy_client_pool_shared_semaphore(httpx_clients):
    """代理请求与直连请求共用并发信号量，不因客户端分离而绕过限流。"""
    assert aiohttpx._req_semaphore is not None
    await aiohttpx.get_client(proxy="http://127.0.0.1:8080")
    assert aiohttpx._req_semaphore is not None


def test_outside_proxy_reads_environment(monkeypatch):
    """OUTSIDE_PROXY 未配置/为空时返回 None，配置后返回原值。"""
    monkeypatch.delenv(OUTSIDE_PROXY_ENV, raising=False)
    assert get_outside_proxy() is None
    monkeypatch.setenv(OUTSIDE_PROXY_ENV, "  http://127.0.0.1:7890  ")
    assert get_outside_proxy() == "http://127.0.0.1:7890"
    monkeypatch.setenv(OUTSIDE_PROXY_ENV, "")
    assert get_outside_proxy() is None


def test_normalize_proxy_socks_scheme():
    """socks:// 归一化为 socks5://，其余原样返回。"""
    assert normalize_proxy("socks://127.0.0.1:1080") == "socks5://127.0.0.1:1080"
    assert normalize_proxy("http://127.0.0.1:7890") == "http://127.0.0.1:7890"
    assert normalize_proxy(None) is None


def test_apply_telegram_proxy(monkeypatch):
    """telegram 未配置时用 OUTSIDE_PROXY 补齐；已配置则尊重原值。"""

    class FakeConfig:
        telegram_proxy = None

    monkeypatch.setenv(OUTSIDE_PROXY_ENV, "http://127.0.0.1:7890")
    config = FakeConfig()
    apply_telegram_proxy(config)
    assert config.telegram_proxy == "http://127.0.0.1:7890"

    config.telegram_proxy = "http://127.0.0.1:9999"
    apply_telegram_proxy(config)
    assert config.telegram_proxy == "http://127.0.0.1:9999"

    monkeypatch.setenv(OUTSIDE_PROXY_ENV, "")
    config.telegram_proxy = None
    apply_telegram_proxy(config)
    assert config.telegram_proxy is None


def test_apply_telegram_proxy_with_nonebot_config(monkeypatch):
    """nonebot Config 链路：注入后 AdapterConfig 能读到 proxy（run.py 真实路径）。"""
    from nonebot.adapters.telegram.config import AdapterConfig
    from nonebot.config import Config

    monkeypatch.setenv(OUTSIDE_PROXY_ENV, "http://127.0.0.1:7890")
    config = Config(_env_file=None, command_start={"/"}, command_sep={"."}, nickname=set())
    apply_telegram_proxy(config)
    adapter_config = AdapterConfig(**config.model_dump())
    assert adapter_config.proxy == "http://127.0.0.1:7890"
