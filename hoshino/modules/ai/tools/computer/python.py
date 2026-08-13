"""computer/python：在冻结工作目录执行 Python 代码。高风险，需显式开启。"""

from __future__ import annotations

from pydantic_ai import RunContext

from ...deps import AgentDeps
from ._runtime import format_result, runner_for


async def python(ctx: RunContext[AgentDeps], code: str) -> str:
    """在冻结工作目录执行 Python 代码片段并返回输出（同 bash 边界）。

    高风险工具：仅当前群被管理员显式开启 computer 类别后才可用；不继承 secrets
    环境变量。请勿执行删除文件、外联等危险操作。
    """
    if not code.strip():
        return "代码不能为空。"
    runner = runner_for(ctx.deps)
    return format_result(await runner.run_python(code))
