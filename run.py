import nonebot
import os
from nonebot.adapters.onebot.v11 import Adapter

moduledir = "hoshino/modules/"
base = "hoshino/base/"
nonebot.init()
driver = nonebot.get_driver()
driver.register_adapter(Adapter)
config = driver.config
nonebot.load_plugin("nonebot_plugin_apscheduler")
nonebot.load_plugins(base)
if modules := config.modules:
    for module in modules:
        module = os.path.join(moduledir, module)
        nonebot.load_plugins(module)

if __name__ == "__main__":
    nonebot.run()
