"""Run-local history compaction and bounded auxiliary model summaries.

只影响单次 Agent run 的内存历史；调用方仍持久化原始事件日志，压缩不丢可审计
数据。

压缩策略（触发 → 远程 → 本地 → 复核）：
1. 估算历史 token，超过 ``compaction_threshold_chars × compaction_threshold_ratio``
   时触发；
2. 远程压缩（预留接口 ``try_remote_compact``，当前恒返回 None 由本地兜底）：
   provider 原生 compact（如 OpenAI Responses ``/responses/compact``）不可用或失败时
   回退本地；
3. 本地压缩：窗口外历史由轻量模型生成摘要，以独立的 user/assistant 消息对注入
   到保留轮之前（与 AstrBot LLMSummaryCompressor 同模式，避免单条消息内多个
   UserPromptPart 的兼容风险）；
4. 复核：压缩后重新估算，仍超阈值时按轮折半截断兜底。
"""

from __future__ import annotations

from typing import Any

from loguru import logger
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    SystemPromptPart,
    TextPart,
    UserPromptPart,
)
from pydantic_ai.models import ModelRequestParameters, ModelSettings

from . import provider, providers
from .deps import AgentDeps

_SUMMARY_PREFIX = "[Earlier context summary]\n"
_ACK_TEXT = "已了解。"
_SUMMARY_INSTRUCTIONS = """Summarize the supplied material for another model continuing the same task.
Keep facts, dates, numbers, source URLs, decisions, tool outcomes, open questions, and constraints.
Do not invent details. Use concise plain text."""

# 图片 token 开销估算（参考 OpenAI vision pricing 中位数，宁可偏高触发压缩）。
_IMAGE_TOKEN_ESTIMATE = 765
# 中文字符 → token 系数与其它字符 → token 系数（AstrBot EstimateTokenCounter 同款）。
_CJK_TOKEN_PER_CHAR = 0.6
_OTHER_TOKEN_PER_CHAR = 0.3


def estimate_tokens(messages: list[ModelMessage]) -> int:
    """估算消息列表的 token 开销（文本按语言、图片按固定值、工具调用按 JSON）。"""
    total = 0
    for message in messages:
        for part in message.parts:
            total += _estimate_part_tokens(part)
    return total


def _estimate_part_tokens(part: Any) -> int:
    """估算单个消息部件的 token 开销（duck-typed，容忍版本差异）。"""
    name = type(part).__name__
    content = getattr(part, "content", None)
    if name == "ToolCallPart":
        args = getattr(part, "args", None)
        return _estimate_text(str(args)) if args is not None else 0
    if isinstance(content, str):
        return _estimate_text(content)
    if isinstance(content, list):
        total = 0
        for item in content:
            if isinstance(item, str):
                total += _estimate_text(item)
            elif type(item).__name__ in ("ImageUrl", "BinaryContent"):
                total += _IMAGE_TOKEN_ESTIMATE
        return total
    return 0


def _estimate_text(text: str) -> int:
    """按字符类型估算 token：中文 0.6/字、其它 0.3/字符。"""
    cjk = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    return int(cjk * _CJK_TOKEN_PER_CHAR + (len(text) - cjk) * _OTHER_TOKEN_PER_CHAR)


def _compaction_threshold(config) -> int:
    """压缩触发的估算 token 阈值（0 或负表示关闭）。"""
    limit = getattr(config, "compaction_threshold_chars", 0) or 0
    if limit <= 0:
        return 0
    ratio = getattr(config, "compaction_threshold_ratio", 0.82) or 0.82
    return max(1, int(limit * min(max(ratio, 0.0), 1.0)))


def message_text_chars(messages: list[ModelMessage]) -> int:
    """Return the approximate text payload size of model messages."""
    total = 0
    for message in messages:
        for part in message.parts:
            content = getattr(part, "content", None)
            if isinstance(content, str):
                total += len(content)
            elif isinstance(content, list):
                total += sum(len(item) for item in content if isinstance(item, str))
    return total


def _history_text(messages: list[ModelMessage]) -> str:
    """Render message parts into bounded-summary input without wire-format internals."""
    lines: list[str] = []
    for message in messages:
        for part in message.parts:
            content = getattr(part, "content", None)
            if isinstance(content, str) and content:
                lines.append(f"{type(part).__name__}: {content}")
            elif isinstance(content, list):
                text_items = [item for item in content if isinstance(item, str)]
                if text_items:
                    lines.append(f"{type(part).__name__}: {''.join(text_items)}")
            elif type(part).__name__ == "ToolCallPart":
                lines.append(f"ToolCallPart: {getattr(part, 'tool_name', '')}")
    return "\n\n".join(lines)


def _first_user_request(messages: list[ModelMessage], start: int) -> int | None:
    """Find a safe retained-round boundary at or after ``start``."""
    for index in range(start, len(messages)):
        message = messages[index]
        if isinstance(message, ModelRequest) and any(
            isinstance(part, UserPromptPart) for part in message.parts
        ):
            return index
    return None


def _user_round_starts(messages: list[ModelMessage]) -> list[int]:
    """所有 user 轮起始下标（用于折半截断按轮对齐）。"""
    return [
        i
        for i, message in enumerate(messages)
        if isinstance(message, ModelRequest)
        and any(isinstance(part, UserPromptPart) for part in message.parts)
    ]


def truncate_by_halving(messages: list[ModelMessage]) -> list[ModelMessage]:
    """压缩后仍超限的兜底：按轮保留最近一半（宁可多丢，不切半轮）。"""
    starts = _user_round_starts(messages)
    if not starts:
        half = len(messages) // 2
        return messages[half:] if half else messages
    keep = max(1, len(starts) // 2)
    boundary = starts[-keep]
    return messages[boundary:]


async def try_remote_compact(
    model: Any,
    request_context: Any,
    messages: list[ModelMessage],
) -> ModelResponse | None:
    """Provider 原生远程压缩（预留接口，当前不启用）。

    未来接入：对支持 ``compact_messages`` 的模型（如 OpenAI Responses）构造
    ``ModelRequestContext`` 并调用，用返回的 ``CompactionPart`` 替换旧历史。
    端点不支持/失败时返回 None，由调用方回退本地压缩。当前恒返回 None。
    """
    compact = getattr(model, "compact_messages", None)
    if compact is None:
        return None
    # 预留：真实实现见
    # https://ai.pydantic.dev/models/ 各 provider 的 message compaction 章节。
    # 当前版本不发起远程压缩请求（DeepSeek OpenAI 端点 /responses/compact 404、
    # Anthropic 端点 CompactionPart 被忽略），由本地摘要兜底。
    return None


async def summarize_text(
    deps: AgentDeps,
    text: str,
    *,
    instructions: str = _SUMMARY_INSTRUCTIONS,
    max_chars: int = 2_000,
    model_name: str = "",
) -> str | None:
    """Use the current provider for a bounded, best-effort auxiliary summary."""
    if not text:
        return None
    record = provider.get_provider(deps.telemetry.provider_id)
    if record is None:
        return None
    selected_model = model_name or deps.config.compaction_model or deps.telemetry.model
    if not selected_model:
        return None

    model = providers.build_auxiliary_model(
        record,
        selected_model,
        proxy=provider.resolve_effective_proxy(record, deps.config.proxy),
    )
    request = ModelRequest(
        parts=[
            SystemPromptPart(content=instructions),
            UserPromptPart(content=text),
        ]
    )
    try:
        response = await model.request(
            [request],
            providers.build_model_settings(record) or ModelSettings(),
            ModelRequestParameters(),
        )
    except Exception as exc:
        logger.warning(
            "AI auxiliary summary failed provider={} model={} error={}",
            record.id,
            selected_model,
            type(exc).__name__,
        )
        return None
    summary = (response.text or "").strip()
    return summary[:max_chars].strip() or None


async def _local_summary_compact(
    deps: AgentDeps,
    messages: list[ModelMessage],
) -> list[ModelMessage] | None:
    """窗口外历史生成摘要，以 user/assistant 消息对注入保留轮之前。"""
    window_size = max(1, getattr(deps.config, "compaction_window_size", 4))
    boundary = _first_user_request(messages, max(0, len(messages) - window_size))
    if boundary is None or boundary == 0:
        return None

    summary = await summarize_text(deps, _history_text(messages[:boundary]))
    if summary is None:
        return None

    summary_pair = [
        ModelRequest(parts=[UserPromptPart(content=f"{_SUMMARY_PREFIX}{summary}")]),
        ModelResponse(parts=[TextPart(content=_ACK_TEXT)]),
    ]
    return [*summary_pair, *messages[boundary:]]


async def compact_history(
    deps: AgentDeps,
    messages: list[ModelMessage],
    *,
    model: Any = None,
    request_context: Any = None,
) -> list[ModelMessage] | None:
    """压缩单次 run 的临时历史；未触发/压缩失败返回 None（保持原历史）。

    ``model``/``request_context`` 供未来远程压缩使用（预留）。
    """
    threshold = _compaction_threshold(deps.config)
    if threshold <= 0 or estimate_tokens(messages) <= threshold:
        return None

    # 远程压缩优先（预留接口；当前恒 None → 本地兜底）。
    if getattr(deps.config, "compaction_remote_first", False):
        try:
            remote = await try_remote_compact(model, request_context, messages)
        except Exception:
            remote = None
        if remote is not None:
            compacted = [remote, *messages[-max(1, deps.config.compaction_window_size) :]]
            if estimate_tokens(compacted) < estimate_tokens(messages):
                return compacted

    compacted = await _local_summary_compact(deps, messages)
    if compacted is None:
        return None

    # 复核：压缩后仍超阈值 → 按轮折半兜底。
    if estimate_tokens(compacted) > threshold:
        compacted = truncate_by_halving(compacted)

    logger.info(
        "AI run history compacted scope={} messages={}→{} tokens={}→{}",
        deps.scope_key,
        len(messages),
        len(compacted),
        estimate_tokens(messages),
        estimate_tokens(compacted),
    )
    return compacted
