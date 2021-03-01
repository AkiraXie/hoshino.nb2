'''
Author: AkiraXie
Date: 2021-02-13 20:24:21
LastEditors: AkiraXie
LastEditTime: 2021-02-15 04:01:21
Description: 
Github: http://github.com/AkiraXie/
'''
from loguru import logger
import random
import string
from hoshino import Service, aiohttpx, Bot
sv = Service('wangyiyun', enable_on_default=False)
shanghao = sv.on_command('上号', aliases=(
    '网抑云', "网易云", "生而为人"), only_group=False)


@shanghao.handle()
async def _(bot: Bot):
    format_string = ''.join(random.sample(
        string.ascii_letters + string.digits, 16))
    try:
        resp = await aiohttpx.get(f'https://nd.2890.ltd/api/?format={format_string}')
        j = resp.json
    except Exception as e:
        logger.exception(e)
        logger.error(type(e))
        await shanghao.finish("调取api失败，请稍后再试")
    if j['status'] !=1:
        await shanghao.finish("请求api失败")
    content=j['data']['content']['content']
    await shanghao.finish(content,call_header=True)