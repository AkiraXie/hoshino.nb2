'''
Author: AkiraXie
Date: 2021-01-31 15:28:12
LastEditors: AkiraXie
LastEditTime: 2021-02-03 13:57:29
Description: 
Github: http://github.com/AkiraXie/
'''
import time
from hoshino.util import load_config, aiohttpx
from loguru import logger
from nonebot import require
Chara = require('chara').Chara


def __get_auth_key():
    config = load_config(__file__)
    return config["AUTH_KEY"]


async def do_query(id_list, region=1):
    id_list = [x * 100 + 1 for x in id_list]
    header = {
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/78.0.3904.87 Safari/537.36',
        'authorization': __get_auth_key()
    }
    payload = {"_sign": "a", "def": id_list, "nonce": "a",
               "page": 1, "sort": 1, "ts": int(time.time()), "region": region}
    logger.debug(f'Arena query {payload=}')
    try:
        resp = await aiohttpx.post('https://api.pcrdfans.com/x/v1/search', headers=header, json=payload)
        res = resp.json
        logger.debug(f'len(res)={len(res)}')
    except Exception as e:
        logger.exception(e)
        return None
    if res['code']:
        logger.error(f"Arena query failed.\nResponse={res}\nPayload={payload}")
        return None

    res = res['data']['result']
    res = [
        {
            'atk': [Chara(c['id'] // 100, c['star'], c['equip']) for c in entry['atk']],
            'up': entry['up'],
            'down': entry['down'],
        } for entry in res
    ]
    return res
