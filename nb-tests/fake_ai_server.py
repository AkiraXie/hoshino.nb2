"""本地 fake HTTP 服务器，模拟 OpenAI / Anthropic 的 ``/chat/completions`` 与 ``/v1/messages``。

供 ai 模块的 provider / chat 集成测试使用：通过真实 HTTP 链路验证请求格式（路径、鉴权
header、body）与响应解析，不连接真实模型、不依赖外网。请求记录列表由测试断言。

实现用标准库 ``ThreadingHTTPServer``：``protocol_version="HTTP/1.1"`` 以兼容 httpx /
openai / anthropic SDK 的 keep-alive；每次响应只调用一次 ``send_response``，避免重复状态行
（HTTP/1.1 下双状态行会让 httpcore 报 ``illegal header line``）。anthropic SDK 会把
``base_url`` 拼成 ``/v1/messages?beta=true``（带 query），故按 ``path.split("?")[0]`` 判路径。
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import ClassVar

OPENAI_RESPONSE = {
    "id": "chatcmpl-fake",
    "object": "chat.completion",
    "created": 1677652288,
    "model": "gpt-4o-mini",
    "choices": [
        {
            "index": 0,
            "message": {"role": "assistant", "content": "你好，我是 OpenAI 回复"},
            "finish_reason": "stop",
        }
    ],
    "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
}

ANTHROPIC_RESPONSE = {
    "id": "msg_fake_01",
    "type": "message",
    "role": "assistant",
    "model": "claude-3-5-sonnet",
    "content": [{"type": "text", "text": "你好，我是 Claude 回复"}],
    "stop_reason": "end_turn",
    "stop_sequence": None,
    "usage": {"input_tokens": 10, "output_tokens": 5},
}

# 原生联网搜索响应（Anthropic web_search_tool_result + citations），
# 供 web_search 工具测试注入：/v1/messages 返回它时，工具应解析出结构化结果。
SEARCH_RESPONSE = {
    "id": "msg_search_01",
    "type": "message",
    "role": "assistant",
    "model": "deepseek-v4-flash",
    "content": [
        {
            "type": "web_search_tool_result",
            "content": [
                {
                    "type": "web_search_result",
                    "url": "https://example.com/result-a",
                    "title": "示例结果 A",
                    "page_age": "2026-08-01",
                },
                {
                    "type": "web_search_result",
                    "url": "https://example.com/result-b",
                    "title": "示例结果 B",
                },
            ],
        },
        {
            "type": "text",
            "text": "以下是搜索到的内容：",
            "citations": [
                {"url": "https://example.com/result-a", "cited_text": "这是结果 A 的摘要。"},
                {"url": "https://example.com/result-b", "cited_text": "这是结果 B 的摘要。"},
            ],
        },
    ],
    "stop_reason": "end_turn",
    "stop_sequence": None,
    "usage": {"input_tokens": 10, "output_tokens": 5},
}

# Tavily /search 响应（results[].title/url/content）。
TAVILY_RESPONSE = {
    "query": "q",
    "results": [
        {
            "title": "Tavily 结果",
            "url": "https://example.com/tavily",
            "content": "这是 Tavily 的摘要。",
            "score": 0.9,
        }
    ],
}

# 博查 /v1/web-search 响应（webPages.value[].name/url/snippet，兼容 Bing 格式）。
BOCHA_RESPONSE = {
    "code": 200,
    "log_id": "log_fake_01",
    "msg": None,
    "data": {
        "_type": "SearchResponse",
        "webPages": {
            "webSearchUrl": "",
            "totalEstimatedMatches": 100,
            "someResultsRemoved": False,
            "value": [
                {
                    "id": None,
                    "name": "博查结果",
                    "url": "https://example.com/bocha",
                    "displayUrl": "https://example.com/bocha",
                    "snippet": "这是博查的摘要。",
                    "siteName": "示例站",
                }
            ],
        },
    },
}


MODELS_RESPONSE = {
    "object": "list",
    "data": [
        {"id": "gpt-4o-mini", "object": "model"},
        {"id": "gpt-4o", "object": "model"},
    ],
}


class _FakeHandler(BaseHTTPRequestHandler):
    """记录每个 POST/GET 请求；按路径返回固定响应。"""

    protocol_version = "HTTP/1.1"
    requests: ClassVar[list[dict]] = []
    custom_response: ClassVar[dict | None] = None  # 测试注入的 /chat/completions 响应
    search_response: ClassVar[dict | None] = None  # 测试注入的 /v1/messages 响应（deepseek 搜索）
    tavily_response: ClassVar[dict | None] = None  # 测试注入的 /search 响应（tavily 搜索）
    bocha_response: ClassVar[dict | None] = None  # 测试注入的 /v1/web-search 响应（博查搜索）

    def _record(self, raw: bytes) -> dict:
        return {
            "path": self.path,
            "stem": self.path.split("?")[0],
            "headers": {k.lower(): v for k, v in self.headers.items()},
            "body": json.loads(raw) if raw else {},
        }

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length)
        stem = self.path.split("?")[0]
        self.requests.append(self._record(raw))
        if stem == "/chat/completions":
            self._respond(200, self.custom_response or OPENAI_RESPONSE)
        elif stem == "/v1/messages":
            self._respond(200, self.search_response or ANTHROPIC_RESPONSE)
        elif stem == "/search":
            self._respond(200, self.tavily_response or TAVILY_RESPONSE)
        elif stem == "/v1/web-search":
            self._respond(200, self.bocha_response or BOCHA_RESPONSE)
        else:
            self._respond(404, {"error": "not found"})

    def do_GET(self) -> None:
        stem = self.path.split("?")[0]
        self.requests.append(self._record(b""))
        if stem == "/models":
            self._respond(200, MODELS_RESPONSE)
        else:
            self._respond(404, {"error": "not found"})

    def _respond(self, status: int, payload: dict) -> None:
        data = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("request-id", "req_fake_1")
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args) -> None:  # 静默，避免污染测试输出
        pass


def start_fake_server(payload: dict | None = None) -> tuple[str, list[dict], callable]:
    """启动 fake HTTP 服务器。

    返回 ``(base_url, requests, stop)``：``base_url`` 可直接作 provider 的 url；
    ``requests`` 是累积的请求记录（每次调用会清空旧的）；``stop`` 关闭服务器。
    ``payload`` 非空时作为 ``/chat/completions`` 的固定响应（用于注入畸形响应，
    如 function_call 字段为 null，验证失败日志携带原始 body 的链路）。
    """
    _FakeHandler.requests = []
    _FakeHandler.custom_response = payload
    _FakeHandler.search_response = None
    _FakeHandler.tavily_response = None
    _FakeHandler.bocha_response = None
    server = ThreadingHTTPServer(("127.0.0.1", 0), _FakeHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"

    def stop() -> None:
        server.shutdown()
        server.server_close()

    return base, _FakeHandler.requests, stop
