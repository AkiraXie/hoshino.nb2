import nonebot
from nonebot.adapters.milky import Adapter as MilkyAdapter
from nonebot.adapters.onebot.v11 import Adapter as OB11Adapter
from nonebot.adapters.telegram import Adapter as TGAdapter

from hoshino.util.proxy import apply_telegram_proxy

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
