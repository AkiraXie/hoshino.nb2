import nonebot
from nonebot.adapters.onebot.v11 import Adapter

from hoshino import config
from hoshino.bootstrap import bootstrap


moduledir = "hoshino/modules/"
base = "hoshino/base/"

# 使用自定义配置初始化nonebot
nonebot.init()
driver = nonebot.get_driver()
driver.register_adapter(Adapter)

# nonebot_plugin_alconna is auto-loaded via hoshino.command imports
nonebot.load_plugin("nonebot_plugin_apscheduler")


bootstrap()

nonebot.load_plugins(base)

if modules := config.modules:
    for module in modules:
        print(f"加载模块: {module}")
        nonebot.load_plugins(config.modules_dir / module)


def main():
    nonebot.run()


if __name__ == "__main__":
    main()
