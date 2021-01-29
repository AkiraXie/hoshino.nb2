'''
Author: AkiraXie
Date: 2021-01-30 01:14:58
LastEditors: AkiraXie
LastEditTime: 2021-01-30 02:33:15
Description: 
Github: http://github.com/AkiraXie/
'''
from loguru import logger
from hoshino import R, Bot, Event
from hoshino.util import Image, BytesIO, aiohttpx, aiorequests, sucmd
import os
os.makedirs( R.img('priconne/icon/'),exist_ok=1)
os.makedirs( R.img('priconne/card/'),exist_ok=1)


async def download_chara_icon(id_, star, rurl='https://api.redive.lolikon.icu/icon/icon_unit_'):
    url = rurl+f'{id_}{star}1.webp'
    save_path = R.img(f'priconne/icon/icon_unit_{id_}{star}1.png').path
    logger.info(f'Downloading chara icon from {url}')
    try:
        rsp = await aiohttpx.get(url)
    except Exception as e:
        logger.error(f'Failed to download {url}. {type(e)}')
        logger.exception(e)
        return 1, star
    if 200 == rsp.status_code:
        img = Image.open(BytesIO(rsp.content))
        img.save(save_path)
        logger.info(f'Saved to {save_path}')
        return 0, star
    else:
        logger.error(f'Failed to download {url}. HTTP {rsp.status_code}')
        return 1, star


async def download_card(id_, star, rurl='https://api.redive.lolikon.icu/bg_still/still_unit_'):
    url = rurl+f'{id_}{star}1.webp'
    save_path = R.img(f'priconne/card/{id_}{star}1.png').path
    logger.info(f'Downloading card from {url}')
    try:
        rsp = await aiohttpx.get(url)
    except Exception as e:
        logger.error(f'Failed to download {url}. {type(e)}')
        logger.exception(e)
        return 1, star
    if 200 == rsp.status_code:
        img = Image.open(BytesIO(rsp.content))
        img.save(save_path)
        logger.info(f'Saved to {save_path}')
        return 0, star
    else:
        logger.error(f'Failed to download {url}. HTTP {rsp.status_code}')
        return 1, star

