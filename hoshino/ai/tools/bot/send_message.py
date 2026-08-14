"""bot/send_message：单向 emit，向当前会话发一条消息。

单向发射：只调 ``send_to_event``，不写历史、不开新 turn（机制层）；NoneBot 不回投自身消息
（系统层）；TOOL_CALL_PROMPT 明文约束依赖场景（语义层）。工具执行时仍需复核 live event。
"""

from __future__ import annotations

from pydantic_ai import RunContext

from ...deps import AgentDeps

_MAX_MESSAGE_CHARS = 2000


async def send_message(ctx: RunContext[AgentDeps], message: str) -> str:
    """向当前会话单向发送一条消息（不开启新对话轮次）。

    仅用于：向用户追问关键信息、耗时动作后的主动通知、工具执行完毕后的结果告知。
    严禁替代最终回复、回应无关消息或发送会再次触发本机器人的内容。
    """
    if not message.strip():
        return "消息不能为空。"
    if len(message) > _MAX_MESSAGE_CHARS:
        return f"消息过长（限 {_MAX_MESSAGE_CHARS} 字符）。"
    if ctx.deps.bot is None or ctx.deps.event is None:
        return "当前环境不支持发送消息。"
    from hoshino.platform import send_to_event

    await send_to_event(ctx.deps.bot, ctx.deps.event, message)
    return "消息已发送。"
