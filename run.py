'''
Author: AkiraXie
Date: 2021-01-27 22:29:46
LastEditors: AkiraXie
LastEditTime: 2021-01-30 02:18:54
Description: 
Github: http://github.com/AkiraXie/
'''
import nonebot
import os

from nonebot.adapters.cqhttp import Bot
log_root = 'logs'
os.makedirs(log_root, exist_ok=True)
moduledir = 'hoshino/modules'
base = 'hoshino/base'
nonebot.init()
driver = nonebot.get_driver()
driver.register_adapter('cqhttp', Bot)
config = driver.config
nonebot.load_builtin_plugins()
nonebot.load_plugins(base)
if modules := config.modules:
    for module in modules:
        module = os.path.join(moduledir, module)
        nonebot.load_plugins(module)
nonebot.get_asgi()


if __name__ == '__main__':
    nonebot.run()
