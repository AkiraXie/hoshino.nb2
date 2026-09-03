"""Run-local history compaction and bounded auxiliary model summaries.

只影响单次 Agent run 的内存历史；调用方仍持久化原始事件日志，压缩不丢可审计
数据。

压缩策略（触发 → 远程 → 本地 → 复核；对齐 dsh compaction 语义）：
1. 估算历史 token，超过 ``compaction_window_tokens × compaction_threshold_ratio``
   （默认 82%）时触发；``compact_history(force=True)`` 用于模型返回“超过窗口”错误
   时的强制压缩（绕过常规阈值）；
2. 远程压缩（预留接口 ``try_remote_compact``，当前恒返回 None 由本地兜底）：
   provider 原生 compact（如 OpenAI Responses ``/responses/compact``）不可用或失败时
   回退本地；
3. 本地压缩：窗口外历史由轻量模型生成摘要（上限 ``compaction_summary_max_tokens``
   token），以独立的 user/assistant 消息对注入到保留 tail 之前；保留 tail 按
   ``window × compaction_retain_ratio``（默认 10%）的 token 预算逐字保留、不切半轮
   （与 AstrBot LLMSummaryCompressor 同模式，避免单条消息内多个 UserPromptPart 的
   兼容风险）；
4. 复核：压缩后重新估算，仍超阈值时按轮折半截断兜底。
"""

from __future__ import annotations

import re
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

from . import models, provider, topic
from .deps import AgentDeps

_SUMMARY_PREFIX = "[Earlier context summary]\n"
_ACK_TEXT = "已了解。"
_SUMMARY_INSTRUCTIONS = """Summarize the supplied material for another model continuing the same task.
Keep facts, dates, numbers, source URLs, decisions, tool outcomes, open questions, and constraints.
Do not invent details. Use concise plain text."""

_SUMMARY_INSTRUCTIONS_TOPIC_AWARE = """Summarize the supplied material for another model continuing the same task.
The material contains multiple distinct topics (marked with [Topic N] headers).
For each topic, provide a separate summary section starting with "【Topic N: <brief title>】".
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


def _compaction_window(config) -> int:
    """估算上下文窗口（token 计数）；0 或负表示关闭压缩。"""
    window = getattr(config, "compaction_window_tokens", 0) or 0
    return int(window) if window > 0 else 0


def _compaction_threshold(config) -> int:
    """压缩触发的估算 token 阈值（0 或负表示关闭）：window × threshold_ratio。"""
    window = _compaction_window(config)
    if window <= 0:
        return 0
    ratio = getattr(config, "compaction_threshold_ratio", 0.82) or 0.82
    return max(1, int(window * min(max(ratio, 0.0), 1.0)))


def _compaction_retain_tokens(config) -> int:
    """逐字保留的上下文 token 预算：window × retain_ratio。"""
    window = _compaction_window(config)
    if window <= 0:
        return 0
    ratio = getattr(config, "compaction_retain_ratio", 0.10) or 0.10
    return max(1, int(window * min(max(ratio, 0.0), 1.0)))


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


def _history_text_with_topics(messages: list[ModelMessage], threshold: float = 0.08) -> str:
    """Render history with topic boundary markers for topic-aware summarization.

    Detects topic boundaries in the message history and annotates each topic
    with a [Topic N] header, making it clear to the summarizer that the history
    contains multiple distinct topics.
    """
    boundaries = topic.detect_topic_boundaries(messages, threshold=threshold)
    if len(boundaries) <= 1:
        # Only one topic, no need for markers
        return _history_text(messages)

    # Multiple topics detected, annotate them
    result_lines: list[str] = []
    for topic_idx, start_idx in enumerate(boundaries):
        end_idx = boundaries[topic_idx + 1] if topic_idx + 1 < len(boundaries) else len(messages)
        topic_messages = messages[start_idx:end_idx]
        result_lines.append(f"\n[Topic {topic_idx + 1}]")
        result_lines.append(_history_text(topic_messages))
    return "\n".join(result_lines)


def _user_round_starts(messages: list[ModelMessage]) -> list[int]:
    """所有 user 轮起始下标（用于折半截断按轮对齐）。"""
    return [
        i
        for i, message in enumerate(messages)
        if isinstance(message, ModelRequest)
        and any(isinstance(part, UserPromptPart) for part in message.parts)
    ]


def _retained_tail_start(messages: list[ModelMessage], retain_tokens: int) -> int:
    """逐字保留尾部的最早消息下标（按 token 预算、不切半轮）。

    从最新消息向前累加估算 token，直到超出 ``retain_tokens``；再把起点对齐到
    最近的「整轮」边界，避免出现与 tool call 脱节的孤儿消息。返回 0 表示整段
    历史都在保留预算内（无可压缩）、或单个超大单元无法安全切分。
    """
    if retain_tokens <= 0 or not messages:
        return 0
    tokens = 0
    index = len(messages)
    while index > 0:
        delta = estimate_tokens([messages[index - 1]])
        if tokens + delta > retain_tokens:
            break
        tokens += delta
        index -= 1
    if index == len(messages) and tokens == 0:
        # 连最新一条消息都超出保留预算 → 仍保留最新一整轮（不可切分单元）。
        starts = _user_round_starts(messages)
        index = starts[-1] if starts else len(messages) - 1
    # 对齐到 index 之前最近的轮边界（整轮保留，宁可略超预算也不切半轮）。
    boundary = 0
    for start in _user_round_starts(messages):
        if start > index:
            break
        boundary = start
    return boundary


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
    max_chars: int = 12_000,
    max_tokens: int = 2048,
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

    model = models.build_auxiliary_model(
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
    settings = models.build_model_settings(record) or {}
    if max_tokens > 0:
        settings = dict(**settings, max_tokens=max_tokens)
    try:
        response = await model.request(
            [request],
            ModelSettings(**settings),
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
    """窗口外历史生成摘要，以 user/assistant 消息对注入保留 tail 之前。

    保留 tail 按 ``window × retain_ratio`` 的 token 预算逐字保留、按整轮对齐，
    不切半轮；窗口外历史交给本地模型摘要。
    """
    retain_tokens = _compaction_retain_tokens(deps.config)
    boundary = _retained_tail_start(messages, retain_tokens)
    if boundary <= 0:
        return None

    # 话题感知摘要：如果启用且检测到多个话题，分别摘要并标注边界
    topic_aware = getattr(deps.config, "compaction_topic_aware", True)
    old_messages = messages[:boundary]
    if topic_aware:
        threshold = getattr(deps.config, "topic_shift_threshold", 0.08)
        history_text = _history_text_with_topics(old_messages, threshold=threshold)
        instructions = _SUMMARY_INSTRUCTIONS_TOPIC_AWARE
    else:
        history_text = _history_text(old_messages)
        instructions = _SUMMARY_INSTRUCTIONS

    max_tokens = getattr(deps.config, "compaction_summary_max_tokens", 2048) or 2048
    summary = await summarize_text(
        deps,
        history_text,
        instructions=instructions,
        max_tokens=max_tokens,
    )
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
    force: bool = False,
) -> list[ModelMessage] | None:
    """压缩单次 run 的临时历史；未触发/压缩失败返回 None（保持原历史）。

    ``force=True`` 用于 provider 确认“超过窗口”后的强制压缩：绕过常规压力阈值
    （模型真实窗口可能小于估算窗口，需无条件压缩再重试）。``model``/
    ``request_context`` 供未来远程压缩使用（预留）。
    """
    window = _compaction_window(deps.config)
    if window <= 0:
        return None
    threshold = _compaction_threshold(deps.config)
    if not force and (threshold <= 0 or estimate_tokens(messages) <= threshold):
        return None

    # 远程压缩优先（预留接口；当前恒 None → 本地兜底）。
    if getattr(deps.config, "compaction_remote_first", False):
        try:
            remote = await try_remote_compact(model, request_context, messages)
        except Exception:
            remote = None
        if remote is not None:
            retain_tokens = _compaction_retain_tokens(deps.config)
            retained_start = _retained_tail_start(messages, retain_tokens)
            compacted = [remote, *messages[retained_start:]]
            if estimate_tokens(compacted) < estimate_tokens(messages):
                return compacted

    compacted = await _local_summary_compact(deps, messages)
    if compacted is None:
        return None

    # 复核：压缩后仍超阈值 → 按轮折半兜底（force 时阈值仍取自窗口，避免过大保留）。
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


# ------------------------------------------------------------ 上下文溢出判定
#
# provider 报告的“请求超过模型上下文窗口”错误（openai_chat 400 / curl 413 等）
# 触发强制压缩重试，与 dsh 的 ``context-overflow`` 触发对齐。

_CONTEXT_OVERFLOW_STATUSES = {400, 408, 413, 414}

_CONTEXT_OVERFLOW_PATTERN = re.compile(
    r"(?:context length|max\w* context|context window|input is too long|"
    r"input text too long|too many tokens|prompt is too long|"
    r"context_length_exceeded|exceeded\w* context|maximum\w* token)"
)


def is_context_overflow(exc: Exception) -> bool:
    """判定 provider 是否报告请求超过模型上下文窗口（触发强制压缩重试）。

    只匹配 4xx 状态码 + 上下文相关短语，避免把“无效 token/授权”等 400 误判为溢出。
    """
    status = getattr(exc, "status_code", None)
    if status not in _CONTEXT_OVERFLOW_STATUSES:
        return False
    text = str(exc)
    for attr in ("body", "message"):
        value = getattr(exc, attr, None)
        if isinstance(value, bytes):
            value = value.decode("utf-8", errors="replace")
        if isinstance(value, str) and value and value not in text:
            text += f" {value}"
    return _CONTEXT_OVERFLOW_PATTERN.search(text.lower()) is not None
