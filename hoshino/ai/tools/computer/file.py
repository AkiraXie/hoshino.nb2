"""computer/file：受限工作目录内的文件读写。

只允许在冻结 workspace 的 root 内操作；解析 symlink 后 containment。敏感路径（.env、
凭据目录、Git 内部文件）直接拒绝，审批不能放行。delete/bulk 为高风险：chat 内返回
“创建 Task”，不产生副作用。
"""

from __future__ import annotations

import asyncio
import os
from typing import Literal

from pydantic_ai import BinaryContent, RunContext

from ... import documents
from ...deps import AgentDeps
from .runtime import computer_workdir

_MAX_WRITE_BYTES = 1024 * 1024
_MAX_READ_CHARS = 50_000
_SENSITIVE_PARTS = (
    ".env",
    "credentials",
    "secrets",
    "id_rsa",
    "id_ed25519",
    ".git",
)

FileMode = Literal["read", "list", "write", "delete"]


def _resolve_contained(root: str, path: str) -> str:
    """解析 path 相对 root 的绝对路径；越界抛 ValueError。"""
    candidate = os.path.abspath(os.path.join(root, path))
    resolved = os.path.realpath(candidate)
    real_root = os.path.realpath(root)
    if not (resolved == real_root or resolved.startswith(real_root + os.sep)):
        raise ValueError("路径越出工作目录。")
    return candidate


def _is_sensitive(resolved: str) -> bool:
    parts = resolved.replace(os.sep, "/").lower().split("/")
    return any(part in _SENSITIVE_PARTS or part.startswith(".env") for part in parts)


# 文件 I/O 同步 helper：经 asyncio.to_thread 在线程池执行，避免阻塞事件循环。
def _list_entries(path: str) -> list[str]:
    return sorted(os.listdir(path))


def _write_text(path: str, content: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


async def file(
    ctx: RunContext[AgentDeps],
    path: str,
    mode: FileMode = "read",
    content: str = "",
) -> str | BinaryContent:
    """在工作目录内读写文件（限 1MB，delete 为高风险）。

    - read <path>：复用 documents 抽取文本/HTML/PDF；图片返回 BinaryContent
    - list <path>：列出目录条目
    - write <path> <content>：写入（将覆盖已有文件）
    - delete <path>：删除（高风险，请创建 Task 由审批流程执行）

    只允许访问工作目录内的路径；敏感路径（.env、凭据、Git 内部文件）直接拒绝。
    """
    root = computer_workdir(ctx.deps.config, ctx.deps)
    os.makedirs(root, exist_ok=True)
    try:
        resolved = _resolve_contained(root, path)
    except ValueError as exc:
        return str(exc)
    if _is_sensitive(resolved):
        return "敏感路径不允许访问。"

    match mode:
        case "read":
            if not os.path.isfile(resolved):
                return f"文件不存在：{path}"
            try:
                data = await documents.file_view(
                    resolved,
                    config=ctx.deps.config,
                    deps=ctx.deps,
                )
            except Exception as exc:
                return f"读取失败：{type(exc).__name__}：{exc}"
            if isinstance(data, str) and len(data) > _MAX_READ_CHARS:
                return f"{data[:_MAX_READ_CHARS]}\n…(截断)"
            return data

        case "list":
            if not os.path.isdir(resolved):
                return f"目录不存在：{path}"
            try:
                entries = await asyncio.to_thread(_list_entries, resolved)
            except OSError as exc:
                return f"列出失败：{exc}"
            if not entries:
                return f"{path} 为空目录。"
            return "\n".join(entries)

        case "write":
            if len(content.encode("utf-8")) > _MAX_WRITE_BYTES:
                return "写入超过 1MB 限制。"
            try:
                await asyncio.to_thread(_write_text, resolved, content)
            except OSError as exc:
                return f"写入失败：{exc}"
            return f"已写入 {path}（{len(content)} 字符）。"

        case "delete":
            return await _delete_file(ctx, resolved, path)

        case _:
            return "未知 mode。"


async def _delete_file(ctx: RunContext[AgentDeps], resolved: str, path: str) -> str:
    """chat surface 拒绝 delete；task surface 经 deferred approval 后实际删除。

    delete 为 high-risk，Task auto 模式下先审批，批准后执行时仍复核
    containment（调用方已做）与路径形态；只删单个文件，不做目录递归（bulk）。
    """
    if ctx.deps.task is None:
        return "delete 为高风险操作，请创建 Task 由审批流程执行。"
    if os.path.isdir(resolved):
        return "不支持删除目录（bulk 操作不在 v1 范围）。"
    if not os.path.isfile(resolved):
        return f"文件不存在：{path}"
    try:
        await asyncio.to_thread(os.remove, resolved)
    except OSError as exc:
        return f"删除失败：{exc}"
    return f"已删除 {path}。"


def risk_for_file(args: dict) -> str:
    """参数级风险：delete 为 high；write 为 medium；read/list 为 low。"""
    match args.get("mode", "read"):
        case "delete":
            return "high"
        case "write":
            return "medium"
        case _:
            return "low"
