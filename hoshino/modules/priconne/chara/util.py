'''
Author: AkiraXie
Date: 2021-01-30 01:14:58
LastEditors: AkiraXie
LastEditTime: 2021-03-15 03:09:38
Description: 
Github: http://github.com/AkiraXie/
'''
from loguru import logger
import requests
from hoshino import R
from hoshino.util import Image, BytesIO, aiohttpx
from hoshino.modules.priconne import pcrdatapath
import os
os.makedirs(R.img('priconne/unit/'), exist_ok=1)
os.makedirs(R.img('priconne/card/'), exist_ok=1)
jsonpath = 'hoshino/service_config/gacha.json'


def download_chara_icon(id_: int, star: int):
    url = f'https://redive.estertion.win/icon/unit/{id_}{star}1.webp'
    save_path = R.img(f'priconne/unit/icon_unit_{id_}{star}1.png').path
    logger.info(f'Downloading chara icon from {url}')
    try:
        rsp = requests.get(url, timeout=5, stream=True,verify=False)
    except Exception as e:
        logger.error(exc := f'Failed to download {url}. {type(e)}')
        logger.exception(e)
        return exc, star
    if 200 == rsp.status_code:
        img = Image.open(BytesIO(rsp.content))
        img.save(save_path)
        logger.info(f'Saved to {save_path}')
        return 0, star
    else:
        logger.error(
            exc := f'Failed to download {url}. HTTP {rsp.status_code}')
        return exc, star


def download_card(id_: int, star: int):
    url = f'https://redive.estertion.win/card/full/{id_}{star}1.webp' if star != 1 else f'https://redive.estertion.win/card/profile/{id_}11.webp'
    save_path = R.img(f'priconne/card/{id_}{star}1.png').path
    logger.info(f'Downloading card from {url}')
    try:
        rsp = requests.get(url, timeout=5, stream=True,verify=False)
    except Exception as e:
        logger.error(exc := f'Failed to download {url}. {type(e)}')
        logger.exception(e)
        return exc, star
    if 200 == rsp.status_code:
        img = Image.open(BytesIO(rsp.content))
        img.save(save_path)
        logger.info(f'Saved to {save_path}')
        return 0, star
    else:
        logger.error(
            exc := f'Failed to download {url}. HTTP {rsp.status_code}')
        return exc, star


async def download_config():
    try:
        dataget = await aiohttpx.get('http://api.akiraxie.cc/pcr/config.json', timeout=5)
        datacon = dataget.content
    except Exception as e:
        logger.error(exc := f'下载配置失败. {type(e)}:{e}')
        logger.exception(e)
        return exc
    if 200 != dataget.status_code:
        logger.error(exc := f'连接服务器失败,HTTP {dataget.status_code}')
        return exc
    with open(jsonpath, 'wb') as f:
        f.write(datacon)
    logger.info('下载卡池配置成功')
    return 0


async def download_pcrdata():
    try:
        dataget = await aiohttpx.get('http://api.akiraxie.cc/pcr/_pcr_data.py', timeout=5)
        datacon = dataget.content
    except Exception as e:
        logger.error(exc := f'下载角色数据失败. {type(e)}:{e}')
        logger.exception(e)
        return exc
    if 200 != dataget.status_code:
        logger.error(exc := f'连接服务器失败,HTTP {dataget.status_code}')
        return exc
    with open(pcrdatapath, 'wb') as f:
        f.write(datacon)
    logger.info('下载角色数据成功')
    return 0
