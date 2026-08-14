"""computer 子进程执行设施（仓库首个 subprocess runner）。

v1 默认实现只在冻结 workspace 的 ``cwd`` 运行，提供超时、输出截断、环境清洗与审计。
**这不是完整 sandbox**（不宣称 filesystem/network 隔离）；产品控制是 scope 绑定、审批、
cwd containment、超时、输出上限与日志审计。后续可替换为 bwrap/Docker 实现，不改变工具 API。
"""

from __future__ import annotations

import asyncio
import os
import sys
from dataclasses import dataclass, field

from hoshino import data_dir

_TIMEOUT_SECONDS = 30.0
_MAX_OUTPUT_CHARS = 20_000
_SENSITIVE_ENV_SUBSTRINGS = (
    "API_KEY",
    "TOKEN",
    "SECRET",
    "PASSWORD",
    "AUTHORIZATION",
    "PROXY",
)


def computer_workdir(config, deps=None) -> str:
    """返回 computer 工具的冻结工作根目录。

    Task 场景优先用冻结的 workspace root（``deps.task.workdir``），否则用
    ``AIConfig.computer_workdir`` 或 ``data/ai_computer``。chat 场景 deps.task 为空，
    行为不变。
    """
    task = getattr(deps, "task", None)
    if task is not None and getattr(task, "workdir", ""):
        return os.path.abspath(os.path.expanduser(task.workdir))
    configured = (config.computer_workdir or "").strip()
    if configured:
        return os.path.abspath(os.path.expanduser(configured))
    return os.path.join(data_dir, "ai_computer")


def _cleaned_env() -> dict[str, str]:
    """剥离凭据/代理相关环境变量，防止子进程继承 secrets。"""
    env = dict(os.environ)
    for key in list(env):
        upper = key.upper()
        if any(sub in upper for sub in _SENSITIVE_ENV_SUBSTRINGS):
            del env[key]
    return env


def _truncate(text: str, limit: int = _MAX_OUTPUT_CHARS) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "\n...[output truncated]"


@dataclass(slots=True)
class SandboxRunner:
    """v1 默认 runner：在给定 cwd 运行命令，超时 + 输出截断 + 环境清洗。"""

    workdir: str
    timeout: float = _TIMEOUT_SECONDS
    max_output_chars: int = _MAX_OUTPUT_CHARS
    _env: dict[str, str] = field(default_factory=_cleaned_env)

    async def run(self, command: str) -> dict[str, object]:
        """异步执行 shell 命令。返回 {exit_code, stdout, stderr, timed_out}。"""
        proc = await asyncio.create_subprocess_shell(
            command,
            cwd=self.workdir,
            env=self._env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        return await self._communicate(proc)

    async def run_python(self, code: str) -> dict[str, object]:
        """异步执行 Python 代码片段。"""
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            "-c",
            code,
            cwd=self.workdir,
            env=self._env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        return await self._communicate(proc)

    async def _communicate(self, proc) -> dict[str, object]:
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=self.timeout
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return {
                "exit_code": -1,
                "stdout": "",
                "stderr": f"[timed out after {self.timeout:.0f}s]",
                "timed_out": True,
            }
        return {
            "exit_code": proc.returncode,
            "stdout": self._truncate(
                stdout.decode("utf-8", "replace"), self.max_output_chars
            ),
            "stderr": self._truncate(
                stderr.decode("utf-8", "replace"), self.max_output_chars
            ),
            "timed_out": False,
        }


def format_result(result: dict[str, object]) -> str:
    """把 SandboxRunner 结果格式化为可读文本。"""
    parts: list[str] = []
    if result["stdout"]:
        parts.append(str(result["stdout"]))
    if result["stderr"]:
        parts.append(f"[stderr]\n{result['stderr']}")
    if not parts:
        parts.append("（无输出）")
    parts.append(f"[exit={result['exit_code']}]")
    if result["timed_out"]:
        parts.append("[超时]")
    return "\n".join(parts)


def runner_for(deps) -> SandboxRunner:
    """构建当前 deps 的 runner，并确保工作根目录存在。"""
    root = computer_workdir(deps.config, deps)
    os.makedirs(root, exist_ok=True)
    return SandboxRunner(workdir=root)
