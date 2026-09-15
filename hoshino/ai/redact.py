"""provider 体脱敏：思考内容不进日志。

日志里能出现思考内容的路径只有两条，都源自 provider 原始体：
- ``models._log_request_payload`` 的请求 dump（历史里回传的 reasoning/thinking）；
- ``errors.format_exception_detail`` 的 ``body=``（pydantic-ai 把原始响应塞进异常）。

本模块把这部分文本替换成规模标记 ``<thinking:N chars>``，保留结构与其余字段，
排障仍能看清「发/收到了哪些 item、思考有多大」，但看不到思考正文。覆盖三种
wire 形态：

- OpenAI Responses：``{"type": "reasoning", "summary"|"content": [{"text": …}]}``；
- OpenAI Chat：``reasoning_content`` / ``reasoning`` 字符串字段；
- Anthropic：``{"type": "thinking", "thinking": …, "signature": …}`` 块。
"""

from __future__ import annotations

import json
import re
from typing import Any

# 承载思考正文的字符串字段（chat 形态）。
_THINKING_TEXT_KEYS = frozenset({"reasoning", "reasoning_content", "thinking_content"})
# 思考 item 类型（responses / anthropic 块）。
_THINKING_ITEM_TYPES = frozenset({"reasoning", "thinking"})
# 思考 item 内的正文 / 摘要 / 签名 / 密文字段。
_THINKING_ITEM_KEYS = frozenset(
    {"content", "summary", "text", "thinking", "signature", "encrypted_content"}
)


def marker(text: str) -> str:
    """思考文本的脱敏标记（保留长度，便于判断规模）。"""
    return f"<thinking:{len(text)} chars>"


# pydantic ValidationError 文本会把出错的 input 原样带出（``input_value=…, input_type=…``），
# Responses 校验失败时这段 input 就是 reasoning item，因此整段抹掉。
_INPUT_VALUE_RE = re.compile(r"input_value=.*?(?=,\s*input_type=|$)", re.DOTALL)


def strip_validation_inputs(text: str) -> str:
    """抹掉 ValidationError 文本里的 ``input_value``（可能内嵌思考原文）。"""
    return _INPUT_VALUE_RE.sub("input_value=<redacted>", text)


def strip_thinking(value: Any) -> Any:
    """递归替换 provider 体里的思考内容，保留其余字段与结构。"""
    if isinstance(value, dict):
        if value.get("type") in _THINKING_ITEM_TYPES:
            return _strip_item(value)
        return {key: _strip_field(key, item) for key, item in value.items()}
    if isinstance(value, list):
        return [strip_thinking(item) for item in value]
    return value


_UNPARSABLE = object()


def strip_thinking_json(text: str) -> str:
    """脱敏 JSON / SSE 文本体；无法解析时原样返回，由调用方决定是否截断。

    provider 的 body 常见两种包装：直接是 JSON，或是「JSON 字符串里再套一段
    SSE/纯文本」（pydantic-ai 把流式原文塞进异常 body 时就是后者），因此解析出
    字符串时再按文本体处理一层。
    """
    parsed = _load_json(text)
    if parsed is _UNPARSABLE:
        return _strip_text_body(text)
    if isinstance(parsed, str):
        return json.dumps(_strip_text_body(parsed), ensure_ascii=False)
    return json.dumps(strip_thinking(parsed), ensure_ascii=False)


def _load_json(text: str) -> Any:
    try:
        return json.loads(text)
    except ValueError:
        return _UNPARSABLE


def _strip_text_body(text: str) -> str:
    """非 JSON 文本体：SSE 逐行脱敏，其他原样返回。"""
    lines = text.splitlines()
    if not any(line.startswith("data:") for line in lines):
        return text
    return "\n".join(_strip_sse_line(line) for line in lines)


def _strip_field(key: str, value: Any) -> Any:
    if isinstance(value, str) and value and key in _THINKING_TEXT_KEYS:
        return marker(value)
    return strip_thinking(value)


def _strip_item(item: dict[str, Any]) -> dict[str, Any]:
    """思考 item：正文/摘要逐段打码，其余字段按普通值递归处理。"""
    cleaned: dict[str, Any] = {}
    for key, value in item.items():
        if key in ("content", "summary") and isinstance(value, list):
            cleaned[key] = [_strip_part(part) for part in value]
        elif key in _THINKING_ITEM_KEYS and isinstance(value, str):
            cleaned[key] = marker(value)
        else:
            cleaned[key] = strip_thinking(value)
    return cleaned


def _strip_part(part: Any) -> Any:
    if isinstance(part, dict) and isinstance(part.get("text"), str):
        return {**part, "text": marker(part["text"])}
    return strip_thinking(part)


def _strip_sse_line(line: str) -> str:
    prefix, separator, payload = line.partition(":")
    body = payload.strip()
    if prefix != "data" or not body or body == "[DONE]":
        return line
    try:
        stripped = json.dumps(strip_thinking(json.loads(body)), ensure_ascii=False)
    except ValueError:
        return line
    return f"{prefix}{separator or ':'} {stripped}"
