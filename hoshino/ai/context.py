"""会话历史裁剪 / 序列化。

``max_history_messages`` 轮次截断；预留 ``ContextCompressor`` 协议，后续可接入
AstrBot 式 token 估算、82% 阈值与 LLM 摘要压缩。

截断按**轮边界**（round）对齐：一轮 = user 提问起，到下一个 user 提问前
（含中间的 tool call / tool return / assistant 回复）。从最旧整轮丢弃，绝不把
一轮拦腰截断——否则会产生没有对应 tool_calls 的孤儿 tool 消息，provider 会 400
（AstrBot round_utils 同款语义）。
"""

from __future__ import annotations

from pydantic_ai.messages import (
    ModelMessage,
    ModelMessagesTypeAdapter,
    ModelRequest,
    ModelResponse,
    TextContent,
    UserPromptPart,
)

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


# ------------------------------------------------------------ 事件日志
#
# 对话历史由 append-only 事件日志派生（可恢复、可重放）。只产三类 surface
# 事件，每类事件 1:1 投影为一条模型消息，因此 ``derive_messages`` 能无损还原：
#   - user/message      → ModelRequest([UserPromptPart])
#   - assistant/message → ModelResponse（序列化整条，含 text + tool_calls）
#   - tool/result       → ModelRequest([ToolReturnPart, ...])（序列化整条）
# 未知事件类型在派生时跳过，保证未来新增事件类型不破坏已有日志的重放。

EVENT_USER_MESSAGE = "user/message"
EVENT_ASSISTANT_MESSAGE = "assistant/message"
EVENT_TOOL_RESULT = "tool/result"

# log-only 事件（可观测/审计，不投影为模型消息）。``derive_messages`` 对它们
# 一律跳过，因此顺序/数量不影响历史重放；落库时与 surface 事件同表追加。
# step 只记录「完成」边界（agent.iter 仅在节点产出后可观测，无法可靠观测 step 开始）。
EVENT_TURN_START = "turn/start"
EVENT_TURN_END = "turn/end"
EVENT_STEP_END = "step/end"
EVENT_TOOL_CALL = "tool/call"
EVENT_REQUEST_HEADER = "request/header"

# 参与模型历史投影的 surface 事件类型；供“消息条数”类计数过滤 log-only 事件。
SURFACE_EVENT_TYPES = (
    EVENT_USER_MESSAGE,
    EVENT_ASSISTANT_MESSAGE,
    EVENT_TOOL_RESULT,
)


def serialize_message(message: ModelMessage) -> str:
    """序列化单条模型消息（复用列表 adapter，取 [0]）。"""
    return ModelMessagesTypeAdapter.dump_json([message]).decode("utf-8")


def deserialize_message(message_json: str) -> ModelMessage | None:
    """反序列化单条模型消息；空/非法返回 None。"""
    if not message_json:
        return None
    try:
        return ModelMessagesTypeAdapter.validate_json(message_json)[0]
    except (ValueError, TypeError, IndexError):
        return None


def _user_prompt_text(part: UserPromptPart) -> str:
    """UserPromptPart 内容转可观测文本：str 直用，多模态部件列表提取文本并标注图片。"""
    content = part.content
    if isinstance(content, str):
        return content
    texts: list[str] = []
    for item in content:
        if isinstance(item, str):
            texts.append(item)
        elif isinstance(item, TextContent):
            texts.append(item.content)
        elif type(item).__name__ in ("ImageUrl", "BinaryContent"):
            texts.append("[图片]")
        else:
            texts.append(str(item))
    return "".join(texts)


def messages_to_events(messages: list[ModelMessage]) -> list[dict]:
    """把消息列表拆成事件序列（迁移与 commit 复用）。

    只产 surface 事件；``ModelRequest`` 含 ``UserPromptPart`` 记为 user/message，
    否则（tool return 或兜底）序列化整条为 tool/result；``ModelResponse`` 序列化
    整条为 assistant/message。user/message 同时保留 ``content``（可观测，多模态
    内容提取文本并标注图片）与 ``message_json``（含 timestamp 的无损重放），保证
    ``derive_messages(messages_to_events(m)) == m`` 字节级往返。
    """
    events: list[dict] = []
    for message in messages:
        if isinstance(message, ModelRequest):
            if any(isinstance(part, UserPromptPart) for part in message.parts):
                content = "".join(
                    _user_prompt_text(part)
                    for part in message.parts
                    if isinstance(part, UserPromptPart)
                )
                events.append(
                    {
                        "type": EVENT_USER_MESSAGE,
                        "data": {
                            "content": content,
                            "message_json": serialize_message(message),
                        },
                    }
                )
            else:
                events.append(
                    {
                        "type": EVENT_TOOL_RESULT,
                        "data": {"message_json": serialize_message(message)},
                    }
                )
        elif isinstance(message, ModelResponse):
            events.append(
                {
                    "type": EVENT_ASSISTANT_MESSAGE,
                    "data": {"message_json": serialize_message(message)},
                }
            )
    return events


def derive_messages(events: list[dict]) -> list[ModelMessage]:
    """把事件序列折叠为模型历史（与 dsh ``deriveMessages`` 同义）。

    只投影三类 surface 事件，log-only / 未知类型跳过。返回的列表每次新建，
    调用方可安全截断/透传。
    """
    messages: list[ModelMessage] = []
    for event in events:
        event_type = event.get("type")
        data = event.get("data") or {}
        if event_type == EVENT_USER_MESSAGE:
            message = deserialize_message(data.get("message_json", ""))
            if message is not None:
                messages.append(message)
            else:
                # 兜底：无 message_json 的旧事件按 content 重建。
                messages.append(
                    ModelRequest(
                        parts=[UserPromptPart(content=data.get("content", ""))]
                    )
                )
        elif event_type in (EVENT_ASSISTANT_MESSAGE, EVENT_TOOL_RESULT):
            message = deserialize_message(data.get("message_json", ""))
            if message is not None:
                messages.append(message)
    return messages


def _is_round_start(message: ModelMessage) -> bool:
    """一轮从「含 user prompt 的 ModelRequest」开始。"""
    return isinstance(message, ModelRequest) and any(
        isinstance(part, UserPromptPart) for part in message.parts
    )


def truncate_messages(
    messages: list[ModelMessage],
    max_messages: int,
) -> list[ModelMessage]:
    """保留最近 ``max_messages`` 条消息；按轮对齐，非正数或 None 表示不裁剪。

    候选切点取 ``len - max_messages``，向后对齐到最近的轮边界（宁可多丢一轮，
    不切半轮）。若最末一轮本身已超长，则整轮保留（不切半轮优先于条数上限）。
    """
    if max_messages is None or max_messages <= 0:
        return list(messages)
    if len(messages) <= max_messages:
        return list(messages)

    boundaries = [i for i, m in enumerate(messages) if _is_round_start(m)]
    if not boundaries:
        # 异常历史（无 user 轮可对齐）：退化为朴素尾部保留。
        return messages[-max_messages:]

    cut = len(messages) - max_messages
    aligned = next((b for b in boundaries if b >= cut), None)
    if aligned is None:
        # 切点落在最后一轮内部 → 保留整个最后一轮。
        return messages[boundaries[-1] :]
    return messages[aligned:]


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
