"""全局境外服务代理配置。

境外服务（steam/x/telegram 等）统一从 ``OUTSIDE_PROXY`` 环境变量读取代理，
不再各自维护配置项。未配置时返回 ``None``（直连）；解析类模块请求不经此
helper，一律直连（见 ``hoshino/util/aiohttpx`` 的 ``trust_env=False``）。
"""

from __future__ import annotations

import os
from typing import Any

OUTSIDE_PROXY_ENV = "OUTSIDE_PROXY"


def get_outside_proxy() -> str | None:
    """返回全局境外服务代理；未配置或为空字符串时返回 ``None``。"""
    proxy = os.getenv(OUTSIDE_PROXY_ENV, "").strip()
    return proxy or None


def normalize_proxy(proxy: str | None) -> str | None:
    """把 ``socks://`` 归一化为 httpx/twscrape 可用的 ``socks5://``。"""
    if proxy and proxy.startswith("socks://"):
        return f"socks5://{proxy.removeprefix('socks://')}"
    return proxy


def apply_telegram_proxy(config: Any) -> None:
    """telegram 未显式配置代理时，用 ``OUTSIDE_PROXY`` 补齐。

    需在 ``nonebot.init()`` 后、adapter 注册前调用：register_adapter 会立刻
    实例化 adapter 并读取 ``config.telegram_proxy``。nonebot Config 对未声明
    的环境变量不生效（extra 只收 dotenv 文件变量），因此直接写 config 对象。
    """
    if getattr(config, "telegram_proxy", None):
        return
    if proxy := get_outside_proxy():
        config.telegram_proxy = proxy


__all__ = [
    "OUTSIDE_PROXY_ENV",
    "apply_telegram_proxy",
    "get_outside_proxy",
    "normalize_proxy",
]
