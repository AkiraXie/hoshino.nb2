"""Run-local history compaction and bounded auxiliary model summaries.

This module only changes the in-memory message history owned by an active Agent
run. Callers keep persisting the original event log, so compaction never loses
auditable conversation data.
"""

from __future__ import annotations

from dataclasses import replace

from loguru import logger
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    SystemPromptPart,
    UserPromptPart,
)
from pydantic_ai.models import ModelRequestParameters, ModelSettings

from . import provider, providers
from .deps import AgentDeps

_SUMMARY_PREFIX = "[Earlier context summary]\n"
_SUMMARY_INSTRUCTIONS = """Summarize the supplied material for another model continuing the same task.
Keep facts, dates, numbers, source URLs, decisions, tool outcomes, open questions, and constraints.
Do not invent details. Use concise plain text."""


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


async def compact_history(
    deps: AgentDeps,
    messages: list[ModelMessage],
) -> list[ModelMessage] | None:
    """Summarize old completed rounds and preserve the newest safe window.

    The summary becomes an additional user part on the first retained user request.
    This avoids splitting tool-call/tool-return pairs or creating a standalone user
    request without a corresponding model response.
    """
    threshold = deps.config.compaction_threshold_chars
    if threshold <= 0 or message_text_chars(messages) <= threshold:
        return None

    window_size = max(1, deps.config.compaction_window_size)
    boundary = _first_user_request(messages, max(0, len(messages) - window_size))
    if boundary is None or boundary == 0:
        return None

    summary = await summarize_text(deps, _history_text(messages[:boundary]))
    if summary is None:
        return None

    retained = list(messages[boundary:])
    first_request = retained[0]
    if not isinstance(first_request, ModelRequest):
        return None
    retained[0] = replace(
        first_request,
        parts=[UserPromptPart(content=f"{_SUMMARY_PREFIX}{summary}"), *first_request.parts],
    )
    logger.info(
        "AI run history compacted scope={} messages={}→{} chars={}→{}",
        deps.scope_key,
        len(messages),
        len(retained),
        message_text_chars(messages),
        message_text_chars(retained),
    )
    return retained
