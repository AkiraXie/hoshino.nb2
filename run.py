"""
Author: AkiraXie
Date: 2021-01-27 22:29:46
LastEditors: AkiraXie
LastEditTime: 2022-02-16 22:54:41
Description: 
Github: http://github.com/AkiraXie/
"""
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
if modules := config.modules:
    for module in modules:
        module = os.path.join(moduledir, module)
        nonebot.load_plugins(module)
nonebot.load_plugins(base)


if __name__ == "__main__":
    nonebot.run()
