"""provider 领域层：DB provider / model-list / scope 模型覆盖与解析。

store 提供表级 CRUD；本层提供领域语义（默认模型解析、model-list 能力校验、
可 hash 的 ``ProviderRecord``，供 Agent 缓存 key 使用）。chat / task / ai_admin
统一走本层，不直接读 config providers（该字段已从 AIConfig 移除）。

模型双维度约定：
- text 模型必填（scope 覆盖 > provider 默认），为空表示配置缺失；
- vision 模型可空（无多模态）；``none`` 是 scope 显式禁用 vision 的哨兵。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from . import store

TEXT_CAPABILITIES = frozenset({"text", "both"})
VISION_CAPABILITIES = frozenset({"multimodal", "both"})
KNOWN_KINDS = ("openai_chat", "openai_responses", "anthropic")

# vision 槽的显式禁用哨兵（scope 覆盖为 ``none`` 时强制关闭多模态）。
VISION_DISABLED = "none"


@dataclass(frozen=True, slots=True)
class ProviderRecord:
    """一个 provider 的不可变快照（可 hash，作 Agent 缓存 key 组件）。"""

    id: str
    url: str = ""
    key: str = ""
    kind: str = "openai_chat"
    default_text_model: str = ""
    default_vision_model: str = ""
    temperature: float | None = None
    max_tokens: int | None = None
    timeout_seconds: float | None = None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "ProviderRecord":
        return cls(
            id=row["id"],
            url=row.get("url", ""),
            key=row.get("key", ""),
            kind=row.get("kind", "openai_chat"),
            default_text_model=row.get("default_text_model", ""),
            default_vision_model=row.get("default_vision_model", ""),
            temperature=row.get("temperature"),
            max_tokens=row.get("max_tokens"),
            timeout_seconds=row.get("timeout_seconds"),
        )


# ---------------------------------------------------------------- provider


def list_providers() -> list[ProviderRecord]:
    return [ProviderRecord.from_row(row) for row in store.list_provider_rows()]


def get_provider(provider_id: str) -> ProviderRecord | None:
    row = store.get_provider_row(provider_id)
    return ProviderRecord.from_row(row) if row is not None else None


def has_provider(provider_id: str) -> bool:
    return store.has_provider_row(provider_id)


def upsert_provider(record: ProviderRecord) -> None:
    store.upsert_provider_row(
        provider_id=record.id,
        url=record.url,
        key=record.key,
        kind=record.kind,
        default_text_model=record.default_text_model,
        default_vision_model=record.default_vision_model,
        temperature=record.temperature,
        max_tokens=record.max_tokens,
        timeout_seconds=record.timeout_seconds,
    )


def remove_provider(provider_id: str) -> bool:
    return store.delete_provider_row(provider_id)


# -------------------------------------------------------------- model-list


def list_models(provider_id: str) -> list[dict[str, str]]:
    return store.list_provider_models(provider_id)


def add_model(provider_id: str, model: str, capabilities: str = "text") -> None:
    store.upsert_provider_model(provider_id, model, capabilities)


def remove_model(provider_id: str, model: str) -> bool:
    return store.delete_provider_model(provider_id, model)


def validate_model_choice(provider_id: str, model: str, slot: str) -> str | None:
    """校验模型在 provider 的 model-list 且能力匹配；返回错误提示或 None。

    ``slot`` ∈ text | vision。vision 的 ``none`` 哨兵直接放行。
    """
    if slot == "vision" and model == VISION_DISABLED:
        return None
    entry = store.get_provider_model(provider_id, model)
    if entry is None:
        return (
            f"模型 `{model}` 不在 provider `{provider_id}` 的 model-list 中，"
            "请先执行 `ai provider model-add` 注册。"
        )
    allowed = TEXT_CAPABILITIES if slot == "text" else VISION_CAPABILITIES
    if entry["capabilities"] not in allowed:
        label = "纯文本" if slot == "text" else "多模态"
        return f"模型 `{model}` 能力为 `{entry['capabilities']}`，不能用作{label}模型。"
    return None


# ---------------------------------------------------------------- 解析


def resolve_models(scope_key: str | None, provider_id: str) -> tuple[str, str]:
    """解析 (text_model, vision_model)。vision 可为空串（无多模态能力）。

    优先级：scope 覆盖 > provider 默认；scope 的 ``none`` 显式禁用 vision。
    provider 不存在或未配置时返回空串，由调用方报配置错误。
    """
    record = get_provider(provider_id)
    if record is None:
        return ("", "")
    overrides = store.get_scope_model_overrides(scope_key or "")
    text = overrides["text_model"] or record.default_text_model
    vision = overrides["vision_model"]
    if vision == VISION_DISABLED:
        vision = ""
    elif not vision:
        vision = record.default_vision_model
    return (text, vision)


def resolve_text_model(scope_key: str | None, provider_id: str) -> str:
    """解析当前 scope 应使用的纯文本模型（task 等不含图 surface 用）。"""
    return resolve_models(scope_key, provider_id)[0]
