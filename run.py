import nonebot
from nonebot.adapters.onebot.v11 import Adapter


moduledir = "hoshino/modules/"
base = "hoshino/base/"

# 使用自定义配置初始化nonebot
nonebot.init()
driver = nonebot.get_driver()
driver.register_adapter(Adapter)

nonebot.load_plugin("nonebot_plugin_apscheduler")
nonebot.load_plugins(base)

from hoshino import config

if modules := config.modules:
    for module in modules:
        nonebot.load_plugins(config.modules_dir / module)


if __name__ == "__main__":
    nonebot.run()
