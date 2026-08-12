"""会话历史裁剪 / 序列化。

首期实现 ``max_history_messages`` 轮次截断；预留 ``ContextCompressor`` 协议，
后续可接入 AstrBot 式 token 估算、82% 阈值与 LLM 摘要压缩。
"""

from __future__ import annotations

from pydantic_ai.messages import ModelMessage, ModelMessagesTypeAdapter

from .config import AIConfig


def serialize_messages(messages: list[ModelMessage]) -> str:
    """把消息列表序列化为 JSON 字符串，配合 SQLite 持久化。"""
    raw = ModelMessagesTypeAdapter.dump_json(messages)
    return raw.decode("utf-8")


def deserialize_messages(messages_json: str | None) -> list[ModelMessage]:
    """从 JSON 字符串还原消息列表；空/非法时返回空列表。"""
    if not messages_json:
        return []
    try:
        return ModelMessagesTypeAdapter.validate_json(messages_json)
    except (ValueError, TypeError):
        return []


def truncate_messages(
    messages: list[ModelMessage],
    max_messages: int,
) -> list[ModelMessage]:
    """保留最近 ``max_messages`` 条消息；非正数或 None 表示不裁剪。"""
    if max_messages is None or max_messages <= 0:
        return list(messages)
    if len(messages) <= max_messages:
        return list(messages)
    return messages[-max_messages:]


def prepare_history(
    scope_key: str,
    messages: list[ModelMessage],
    config: AIConfig,
) -> list[ModelMessage]:
    """发送给模型前处理好的历史。首期仅做轮次截断。"""
    return truncate_messages(messages, config.max_history_messages)


class ContextCompressor:
    """上下文压缩协议。首期仅透传，后续接入 token 估算与 LLM 摘要。"""

    def compress(
        self,
        scope_key: str,
        messages: list[ModelMessage],
        config: AIConfig,
    ) -> list[ModelMessage]:
        return prepare_history(scope_key, messages, config)
