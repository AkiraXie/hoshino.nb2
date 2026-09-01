"""provider 领域层：DB provider / model-list / scope 模型覆盖与解析。

store 提供表级 CRUD；本层提供领域语义（模型解析、可 hash 的 ``ProviderRecord``，
供 Agent 缓存 key 使用）。chat / task / ai_admin 统一走本层。

模型约定（唯一槽）：
- scope 覆盖（``ai model set``）> 全局默认（``ai model default``）；
- 两级都空 → 未配置（由调用方提示 ``ai model default``）；
- provider 行只提供连接（url/key/kind/代理/采样），不再提供默认模型名。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from hoshino.util.proxy import get_outside_proxy

from . import store

KNOWN_KINDS = ("openai_chat", "openai_responses", "anthropic")

# 全局默认 model 配置的 KV key（``ai model default`` 写入）。
MODEL_GLOBAL_PROVIDER = "default_model_provider"
MODEL_GLOBAL_MODEL = "default_model"


@dataclass(frozen=True, slots=True)
class ProviderRecord:
    """一个 provider 的不可变快照（可 hash，作 Agent 缓存 key 组件）。"""

    id: str
    url: str = ""
    key: str = ""
    kind: str = "openai_chat"
    use_proxy: bool = False
    temperature: float | None = None
    max_tokens: int | None = None
    timeout_seconds: float | None = None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> ProviderRecord:
        return cls(
            id=row["id"],
            url=row.get("url", ""),
            key=row.get("key", ""),
            kind=row.get("kind", "openai_chat"),
            use_proxy=bool(row.get("use_proxy", False)),
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
        default_text_model="",  # 列保留不读；领域层不再写默认模型
        use_proxy=record.use_proxy,
        temperature=record.temperature,
        max_tokens=record.max_tokens,
        timeout_seconds=record.timeout_seconds,
    )


def remove_provider(provider_id: str) -> bool:
    return store.delete_provider_row(provider_id)


def resolve_effective_proxy(record: ProviderRecord, config_proxy: str | None) -> str | None:
    """provider 实际使用的代理。

    ``use_proxy=True`` 时优先走 AI 配置的代理（未配置回退全局 ``OUTSIDE_PROXY``）；
    默认（False）返回 ``None`` 直连，不走任何代理。
    """
    if record.use_proxy:
        return config_proxy or get_outside_proxy()
    return None


def resolve_tool_proxy(config_proxy: str | None, *, tool_use_proxy: bool) -> str | None:
    """web/browser 等抓取类工具实际使用的代理。

    ``tool_use_proxy=True`` 时优先走 AI 配置的代理（未配置回退全局
    ``OUTSIDE_PROXY``），并归一化 ``socks://`` 为 httpx/Playwright 可解析的
    ``socks5://``；默认（False）返回 ``None`` 直连，与既有解析类请求直连策略一致。
    """
    if not tool_use_proxy:
        return None
    return _normalize_proxy(config_proxy or get_outside_proxy())


# ------------------------------------------------------------ 可用模型（实时）

# 本地不再维护 model-list（ai_provider_models 表仅作历史迁移用途）：可用模型
# 一律调用 provider API 实时获取，避免与网关侧模型更新脱节。


def _normalize_proxy(proxy: str | None) -> str | None:
    if proxy and proxy.startswith("socks://"):
        return f"socks5://{proxy.removeprefix('socks://')}"
    return proxy


async def fetch_available_models(
    record: ProviderRecord,
    *,
    proxy: str | None = None,
    verify: bool = True,
    timeout: float = 15.0,
) -> list[str] | None:
    """调用 provider API 获取真实可用模型列表（openai / anthropic 兼容端点）。

    openai_chat / openai_responses 走 ``GET {url}/models``（Bearer 鉴权）；
    anthropic 依次尝试 ``{url}/v1/models`` 与 ``{url}/models``（x-api-key）。
    网络/鉴权/端点不支持等任何失败返回 None，由调用方给出提示。
    """
    import httpx

    if not record.url or not record.key:
        return None
    base = record.url.rstrip("/")
    if record.kind == "anthropic":
        headers = {"x-api-key": record.key, "anthropic-version": "2023-06-01"}
        candidates = (f"{base}/v1/models", f"{base}/models")
    else:
        headers = {"Authorization": f"Bearer {record.key}"}
        candidates = (f"{base}/models",)

    async with httpx.AsyncClient(
        proxy=_normalize_proxy(proxy),
        trust_env=False,
        verify=verify,
        timeout=httpx.Timeout(timeout),
        follow_redirects=True,
    ) as client:
        for url in candidates:
            try:
                response = await client.get(url, headers=headers)
                response.raise_for_status()
                data = response.json()
            except (httpx.HTTPError, ValueError):
                continue
            rows = data.get("data") if isinstance(data, dict) else None
            if not isinstance(rows, list):
                continue
            ids = [str(row.get("id")) for row in rows if isinstance(row, dict) and row.get("id")]
            if ids:
                return sorted(ids)
    return None


# ---------------------------------------------------------------- 解析


def resolve_model(scope_key: str | None) -> tuple[str, str]:
    """解析当前 scope 应使用的 (provider_id, model)。

    优先级：
    1. scope 的 provider + model 覆盖（``ai model set``）；
    2. 全局默认（``ai model default``）。

    两级都空或 provider 不存在时返回 ``("", "")``。
    """
    overrides = store.get_scope_model_overrides(scope_key or "")
    if overrides["provider"] and overrides["model"] and has_provider(overrides["provider"]):
        return overrides["provider"], overrides["model"]

    g_pid = store.get_global_value(MODEL_GLOBAL_PROVIDER) or ""
    g_model = store.get_global_value(MODEL_GLOBAL_MODEL) or ""
    if g_pid and g_model and has_provider(g_pid):
        return g_pid, g_model
    return "", ""
