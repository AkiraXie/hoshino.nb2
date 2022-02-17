"""
Author: AkiraXie
Date: 2021-03-16 13:25:18
LastEditors: AkiraXie
LastEditTime: 2021-03-16 22:38:39
Description: 
Github: http://github.com/AkiraXie/
"""
from .aiohttpx import post
from hoshino import hsn_config

token: str = hsn_config.bitly_token if "bitly_token" in hsn_config.dict() else ""
guid: str = hsn_config.bitly_guid if "bitly_guid" in hsn_config.dict() else ""

headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


async def get_bitly_url(url: str) -> str:
    if not token or not guid:
        return url
    data = {
        "long_url": url,
        "domain": "bit.ly",
        "group_guid": guid,
    }
    try:
        resp = await post(
            "https://api-ssl.bitly.com/v4/shorten", json=data, headers=headers
        )
        j = resp.json
        return j["link"]
    except:
        return url
