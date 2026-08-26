"""全局境外服务代理配置。

境外服务（steam/x/telegram 等）统一从 ``OUTSIDE_PROXY`` 环境变量读取代理，
不再各自维护配置项。未配置时返回 ``None``（直连）；解析类模块请求不经此
helper，一律直连（见 ``hoshino/util/aiohttpx`` 的 ``trust_env=False``）。
"""

from __future__ import annotations

import os
from typing import Any

OUTSIDE_PROXY_ENV = "OUTSIDE_PROXY"


def _env_file_value(key: str, path: str = ".env.prod") -> str | None:
    """从 env 文件读取单个键值（dotenv 只进 nonebot config，不写 os.environ）。"""
    try:
        with open(path, encoding="utf-8") as fh:
            for raw in fh:
                line = raw.strip()
                if line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                if k.strip() == key:
                    return v.strip().strip('"').strip("'") or None
    except OSError:
        return None
    return None


def get_outside_proxy() -> str | None:
    """返回全局境外服务代理；未配置或为空字符串时返回 ``None``。

    优先读 ``OUTSIDE_PROXY`` 环境变量，回退 ``.env.prod`` 文件——后者由
    dotenv 加载进 nonebot config 但不会写回 ``os.environ``，不回退会导致
    x/steam 等读环境变量的模块拿不到代理而直连超时。
    """
    proxy = os.getenv(OUTSIDE_PROXY_ENV, "").strip()
    return proxy or _env_file_value(OUTSIDE_PROXY_ENV)


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
