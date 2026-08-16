"""core/memory：scope 隔离的长期记忆读写。"""

from __future__ import annotations

from typing import Literal

from pydantic_ai import RunContext

from ... import store
from ...deps import AgentDeps

_MAX_VALUE_LENGTH = 2000
_MAX_KEYS = 100

MemoryAction = Literal["get", "set", "delete", "list"]


async def memory(
    ctx: RunContext[AgentDeps],
    action: MemoryAction = "list",
    key: str = "",
    value: str = "",
) -> str:
    """读写当前会话 scope 的长期记忆。

    - get <key>：读取指定 key 的值
    - set <key> <value>：写入（值限 2000 字符，单 scope 限 100 条）
    - delete <key>：删除指定 key
    - list：列出全部 key

    记忆按 scope 隔离，只对当前会话可见；其他群/用户互不影响。
    """
    scope_key = ctx.deps.scope_key or ""
    if not scope_key:
        return "当前环境不支持记忆（无法解析 scope）。"

    match action:
        case "get":
            if not key:
                return "get 需要 key 参数。"
            value = store.memory_get(scope_key, key)
            return value if value is not None else f"记忆 `{key}` 不存在。"

        case "set":
            if not key:
                return "set 需要 key 参数。"
            if not value:
                return "set 需要 value 参数。"
            if len(value) > _MAX_VALUE_LENGTH:
                return f"value 超过 {_MAX_VALUE_LENGTH} 字符限制。"
            keys = store.memory_list_keys(scope_key)
            if key not in keys and len(keys) >= _MAX_KEYS:
                return f"记忆条数超过 {_MAX_KEYS} 上限，请先 delete 一些。"
            store.memory_set(scope_key, key, value)
            return f"已写入记忆 `{key}`。"

        case "delete":
            if not key:
                return "delete 需要 key 参数。"
            if store.memory_delete(scope_key, key):
                return f"已删除记忆 `{key}`。"
            return f"记忆 `{key}` 不存在。"

        case "list":
            keys = store.memory_list_keys(scope_key)
            if not keys:
                return "暂无记忆。"
            return "记忆 keys：" + "、".join(keys)

        case _:
            return "未知操作。"
