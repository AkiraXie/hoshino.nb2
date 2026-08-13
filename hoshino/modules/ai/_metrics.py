"""token / cache 用量指标提取与聚合展示。

从 Pydantic AI ``RunResult.usage()`` 提取用量，落到 SQLite（``store.record_usage_event``），
并提供缓存命中率计算与 ``ai stats`` 展示文本。
"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic_ai.usage import RunUsage

from . import _store as store


@dataclass(frozen=True, slots=True)
class UsageSnapshot:
    """一次请求的用量快照。字段缺失时默认为 0。"""

    request_tokens: int = 0
    response_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    requests: int = 0

    @property
    def total_tokens(self) -> int:
        return self.request_tokens + self.response_tokens


def _int_or_zero(value: int | None) -> int:
    return value if value is not None else 0


def snapshot_from_usage(usage: RunUsage | None) -> UsageSnapshot:
    """从 Pydantic AI RunUsage 提取快照；缺失字段填 0。"""
    if usage is None:
        return UsageSnapshot()
    return UsageSnapshot(
        request_tokens=_int_or_zero(usage.input_tokens),
        response_tokens=_int_or_zero(usage.output_tokens),
        cache_read_tokens=_int_or_zero(usage.cache_read_tokens),
        cache_write_tokens=_int_or_zero(usage.cache_write_tokens),
        requests=_int_or_zero(usage.requests),
    )


def snapshot_from_result(result: object) -> UsageSnapshot:
    """从 RunResult 对象提取用量。result.usage() 可能返回 None。"""
    usage = getattr(result, "usage", None)
    if callable(usage):
        usage = usage()
    return snapshot_from_usage(usage)


def record_success(
    *,
    provider_id: str,
    scope_key: str,
    model: str,
    snapshot: UsageSnapshot,
    latency_ms: float,
) -> None:
    """记录一次成功请求的用量。"""
    store.record_usage_event(
        provider_id=provider_id,
        scope_key=scope_key,
        model=model,
        request_tokens=snapshot.request_tokens,
        response_tokens=snapshot.response_tokens,
        cache_read_tokens=snapshot.cache_read_tokens,
        cache_write_tokens=snapshot.cache_write_tokens,
        latency_ms=latency_ms,
        error=None,
    )


def record_error(
    *,
    provider_id: str,
    scope_key: str,
    model: str,
    latency_ms: float,
    error: str,
) -> None:
    """记录一次失败请求（不消耗 token 或无法取得用量）。"""
    store.record_usage_event(
        provider_id=provider_id,
        scope_key=scope_key,
        model=model,
        latency_ms=latency_ms,
        error=error[:500] or "error",
    )


def cache_hit_ratio(request_tokens: int, cache_read_tokens: int) -> float:
    """缓存命中率 = cache_read / (cache_read + request_tokens)。"""
    denominator = cache_read_tokens + request_tokens
    if denominator <= 0:
        return 0.0
    return cache_read_tokens / denominator


def format_stats(
    aggregate: dict,
    *,
    provider_id: str | None = None,
    model_name: str = "",
) -> str:
    """把 aggregate_usage 的结果格式化为可读文本。"""
    label = f"provider `{provider_id}`" if provider_id else "全部 provider"
    hit = cache_hit_ratio(aggregate["request_tokens"], aggregate["cache_read_tokens"])
    lines = [
        f"AI 用量统计（{label}）：",
        f"事件数：{aggregate['events']}（成功 {aggregate['success_count']} / 失败 {aggregate['error_count']}）",
        f"总 token：{aggregate['total_tokens']}（输入 {aggregate['request_tokens']} / 输出 {aggregate['response_tokens']}）",
        f"缓存：read {aggregate['cache_read_tokens']} / write {aggregate['cache_write_tokens']}，命中率 {hit:.1%}",
        f"平均延迟：{aggregate['avg_latency_ms']:.0f} ms",
    ]
    if model_name:
        lines.insert(1, f"模型：{model_name}")
    return "\n".join(lines)
