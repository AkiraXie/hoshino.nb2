import os

import nonebot
from nonebot.adapters.milky import Adapter as MilkyAdapter
from nonebot.adapters.onebot.v11 import Adapter as OB11Adapter
from nonebot.adapters.telegram import Adapter as TGAdapter

from hoshino.util.proxy import apply_telegram_proxy


def _sanitize_proxy_env() -> None:
    """移除 httpx 无法处理的代理环境变量，避免 driver 创建客户端时崩溃。

    httpx 只接受 socks5:// / socks5h://（且需 socksio），遇到 socks:// 会直接抛
    ValueError；no_proxy 里的方括号 IPv6（如 [::1]）会让 httpx 0.28 抛
    InvalidURL。nonebot 的 httpx driver 固定 trust_env=True 且没有配置项，于是
    Milky 反连的 HTTP 调用会失败。境外服务的代理由 .env.prod 的 OUTSIDE_PROXY /
    telegram_proxy 等显式配置，不依赖这些环境变量。
    """
    for name in ("ALL_PROXY", "all_proxy"):
        os.environ.pop(name, None)
    for name in ("NO_PROXY", "no_proxy"):
        value = os.environ.get(name)
        if value is None:
            continue
        entries = [
            entry
            for entry in value.split(",")
            if entry.strip() and not entry.strip().startswith("[")
        ]
        if entries:
            os.environ[name] = ",".join(entries)
        else:
            os.environ.pop(name, None)


_sanitize_proxy_env()

# 使用自定义配置初始化nonebot
nonebot.init()
driver = nonebot.get_driver()

# telegram 未显式配置代理时，统一使用全局 OUTSIDE_PROXY（须在 adapter 注册前）
apply_telegram_proxy(driver.config)

driver.register_adapter(OB11Adapter)
driver.register_adapter(TGAdapter)  # Telegram adapter
driver.register_adapter(MilkyAdapter)  # Milky QQ client adapter

# 必须在任何 hoshino 模块导入之前加载 alconna ——
# hoshino 的 import 链会经过 platform.message/target，最终 import
# nonebot_plugin_alconna.uniseg。
# 会把它当作普通模块 import；若此刻尚未作为 plugin 注册，NoneBot 会抛
# RuntimeError: not loaded as a plugin，所有 Alconna matcher 静默失效。
nonebot.load_plugin("nonebot_plugin_apscheduler")
nonebot.load_plugin("nonebot_plugin_alconna")
nonebot.load_plugin("nonebot_plugin_uninfo")

# 延后到 alconna 注册完成后再 import hoshino
from hoshino import config  # noqa: E402
from hoshino.bootstrap import bootstrap  # noqa: E402

base = "hoshino/base/"

bootstrap()

nonebot.load_plugins(base)

if modules := config.modules:
    for module in modules:
        nonebot.load_plugins(config.modules_dir / module)

# 验证：打印实际加载的插件总数
_loaded = [p for p in nonebot.get_loaded_plugins() if p.name]
_avail = nonebot.get_available_plugin_names()
print(f"插件加载完成: {len(_loaded)} loaded / {len(_avail)} available")


def main():
    nonebot.run()


if __name__ == "__main__":
    main()
