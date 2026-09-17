"""拦截「只吐一句预告文本就当最终回复」。

chat Agent 以 ``TextOutput(guard_reply)`` 接入：模型在有工具可用、本轮还没真正
调过工具时，用短预告（「先查一下…」）终局会被 ``ModelRetry`` 同轮打回一次。
``result.output`` 仍是 ``str``，wire 仍是纯文本。Task 的 run 级 ``output_type``
覆盖本 guard，不受影响。
"""

from __future__ import annotations

import re

from loguru import logger
from pydantic_ai import ModelRetry, RunContext
from pydantic_ai.messages import ToolReturnPart, UserPromptPart

from .deps import AgentDeps
from .tools import resolve_tools

# 宁可漏不误伤：只拦「极短 + 开口就是预告」；长文里偶然出现「先查」不命中。
PREAMBLE_MAX_CHARS = 80
_PREAMBLE_OPENER = re.compile(
    r"^(等我|让我|我先|我去|先(?:查|搜|看)|稍等|(?:这个问题)?得查|帮你查|let me |i(?:'ll| will) )",
    re.IGNORECASE,
)
_RETRY_HINT = (
    "不要只口头预告「我先查/我先搜」。需要外部信息时立刻调用工具；"
    "若这个问题不需要工具，请直接给出完整回答。"
)


def is_tool_preamble(text: str) -> bool:
    """短文本且开头是预告口吻（「先查一下」「等我搜」等）。"""
    stripped = text.strip()
    if not stripped or len(stripped) > PREAMBLE_MAX_CHARS:
        return False
    return _PREAMBLE_OPENER.search(stripped) is not None


def _used_tools_this_turn(ctx: RunContext[AgentDeps]) -> bool:
    """当前用户提问之后是否已有工具返回（忽略更早轮次的历史）。"""
    after_user = False
    for message in ctx.messages:
        for part in getattr(message, "parts", ()):
            if isinstance(part, UserPromptPart):
                after_user = True
            elif after_user and isinstance(part, ToolReturnPart):
                return True
    return False


async def guard_reply(ctx: RunContext[AgentDeps], text: str) -> str:
    """文本将要终局时调用：命中预告且还可重试则 ``ModelRetry``，否则原样返回。"""
    # 文本终局路径上 ``available_tool_names`` 不一定已填满；用本轮实际注入的工具集。
    if ctx.last_attempt or not resolve_tools(ctx.deps) or _used_tools_this_turn(ctx):
        return text
    if not is_tool_preamble(text):
        return text
    tel = ctx.deps.telemetry
    logger.info(
        "AI 预告文本打回 provider={} scope={} conv={} chars={} preview={}",
        tel.provider_id,
        ctx.deps.scope_key or tel.scope_key,
        tel.conversation_id,
        len(text),
        text.strip(),
    )
    raise ModelRetry(_RETRY_HINT)
