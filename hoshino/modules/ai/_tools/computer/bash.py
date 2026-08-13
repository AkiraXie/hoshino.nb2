"""computer/bash：在冻结工作目录执行 shell 命令。高风险，需显式开启。"""

from __future__ import annotations

from pydantic_ai import RunContext

from ..._deps import AgentDeps
from ._runtime import format_result, runner_for


async def bash(ctx: RunContext[AgentDeps], command: str) -> str:
    """在冻结工作目录执行 shell 命令并返回输出（限 30 秒、20k 字符）。

    高风险工具：仅当前群被管理员显式开启 computer 类别后才可用；避免 rm -rf、
    格式化、内网探测、外联等危险操作。不继承 secrets 环境变量。
    """
    if not command.strip():
        return "命令不能为空。"
    runner = runner_for(ctx.deps)
    return format_result(await runner.run(command))
