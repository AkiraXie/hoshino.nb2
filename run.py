'''
Author: AkiraXie
Date: 2021-01-27 22:29:46
LastEditors: AkiraXie
LastEditTime: 2021-02-03 14:08:16
Description: 
Github: http://github.com/AkiraXie/
'''
import nonebot
import os
from loguru import logger
from nonebot.adapters.cqhttp import Bot
log_root = 'logs/'
os.makedirs(log_root, exist_ok=True)
logger.add(log_root+'hsn{time:YYYYMMDD}.log', rotation='00:00',level='INFO')
logger.add(log_root+'hsn{time:YYYYMMDD}_error.log', rotation='00:00',level='ERROR')
moduledir = 'hoshino/modules/'
base = 'hoshino/base/'
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
