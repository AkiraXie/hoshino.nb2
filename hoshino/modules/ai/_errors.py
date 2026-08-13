"""异常详情提取：让失败日志不只是异常类名。

背景：此前 ``error={type(exc).__name__}`` 只记录异常类名，``UnexpectedModelBehavior``
这类 pydantic-ai 异常的真实原因（message + 原始 response body，body 常包含模型返回的
非法工具调用或不可解析内容）完全不可见。本模块从常见异常中提取关键字段，供 chat/task
的失败日志与 usage event 的 error 列使用。

约定：
- 只提取字段文本，不打印 traceback（traceback 由调用方按 DEBUG 级别用 exc_info 记录）；
- 输出默认截断到 800 字符，避免 model 原始 body 刷屏；
- 字段访问全部 duck-typed：pydantic-ai 升级导致字段改名时回退 str/repr，不抛错。
"""

from __future__ import annotations

_GROUP_NAMES = ("ExceptionGroup", "BaseExceptionGroup")
_DEFAULT_LIMIT = 800


def _truncate(text: str, limit: int) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return f"{text[:limit]}...(truncated {len(text) - limit} chars)"


def _body_text(body) -> str | None:
    """body 可能是 str / dict / list / None；统一成字符串，避免 repr 刷屏。"""
    if body is None:
        return None
    if isinstance(body, str):
        return body
    try:
        import json

        return json.dumps(body, ensure_ascii=False)
    except Exception:
        return repr(body)


def format_exception_detail(exc: BaseException, limit: int = _DEFAULT_LIMIT) -> str:
    """把异常压成一段可读详情（message + status/body/tool，截断）。

    已知类型：``UnexpectedModelBehavior`` / ``ModelHTTPError`` /
    ``ToolFailedError`` / ``ToolRetryError`` / ``ExceptionGroup``；
    未知类型回退 ``str`` / ``repr``，绝不因提取失败吞掉错误。
    """
    # ExceptionGroup：聚合子异常，避免只看到顶层 "unhandled errors in a TaskGroup"。
    if type(exc).__name__ in _GROUP_NAMES:
        children = list(getattr(exc, "exceptions", []) or [])
        if children:
            return _truncate(
                "; ".join(
                    format_exception_detail(child, limit=limit) for child in children
                ),
                limit,
            )

    # 工具异常（ToolFailedError / ToolRetryError）把 tool_name 包在
    # .tool_failed / .tool_retry 上，先尝试从包装对象取工具名。
    tool_name = getattr(exc, "tool_name", None)
    if tool_name is None:
        for attr in ("tool_failed", "tool_retry"):
            wrapped = getattr(exc, attr, None)
            if wrapped is not None:
                tool_name = getattr(wrapped, "tool_name", None) or tool_name
                break

    message = getattr(exc, "message", None) or str(exc)
    status_code = getattr(exc, "status_code", None)
    body = _body_text(getattr(exc, "body", None))

    parts: list[str] = []
    if tool_name:
        parts.append(f"tool={tool_name}")
    if status_code is not None:
        parts.append(f"status={status_code}")
    if message:
        parts.append(str(message).strip())
    if body:
        parts.append(f"body={body.strip()}")

    if parts:
        return _truncate(" ".join(parts), limit)
    return _truncate(repr(exc), limit)
