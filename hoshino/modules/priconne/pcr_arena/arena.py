"""
Author: AkiraXie
Date: 2021-01-31 15:28:12
LastEditors: AkiraXie
LastEditTime: 2021-04-15 15:05:13
Description: 
Github: http://github.com/AkiraXie/
"""
import time
from hoshino.util import aiohttpx
from . import sv, Chara


def __get_auth_key():
    config = sv.config
    return config["AUTH_KEY"]


async def do_query(id_list, region=1):
    id_list = [x * 100 + 1 for x in id_list]
    header = {
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/78.0.3904.87 Safari/537.36",
        "authorization": __get_auth_key(),
    }
    payload = {
        "_sign": "a",
        "def": id_list,
        "nonce": "a",
        "page": 1,
        "sort": 1,
        "ts": int(time.time()),
        "region": region,
    }
    sv.logger.debug(f"Arena query {payload=}")
    try:
        resp = await aiohttpx.post(
            "https://api.pcrdfans.com/x/v1/search", headers=header, json=payload
        )
        res = resp.json
        sv.logger.debug(f"len(res)={len(res)}")
    except Exception as e:
        sv.logger.exception(e)
        return None
    if res["code"]:
        sv.logger.error(f"Arena query failed.\nResponse={res}\nPayload={payload}")
        return None

    res = res["data"]["result"]
    res = [
        {
            "atk": [Chara(c["id"] // 100, c["star"], c["equip"]) for c in entry["atk"]],
            "up": entry["up"],
            "down": entry["down"],
        }
        for entry in res
    ]
    return res
