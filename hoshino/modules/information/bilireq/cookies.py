import re
from Crypto.Cipher import PKCS1_OAEP
from Crypto.PublicKey import RSA
from Crypto.Hash import SHA256
import binascii
import time
from hoshino.util.aiohttpx import get, post



key = RSA.importKey('''\
-----BEGIN PUBLIC KEY-----
MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQDLgd2OAkcGVtoE3ThUREbio0Eg
Uc/prcajMKXvkCKFCWhJYJcLkcM2DKKcSeFpD/j6Boy538YXnR6VhcuUJOhH2x71
nzPjfdTcqMz7djHum0qSZA0AyCBDABUqCrfNgCiJ00Ra7GmRj+YCK1NJEuewlb40
JNrRuoEUXpabUzGB8QIDAQAB
-----END PUBLIC KEY-----''')

def getCorrespondPath():
    ts = round(time.time() * 1000)
    cipher = PKCS1_OAEP.new(key, SHA256)
    encrypted = cipher.encrypt(f'refresh_{ts}'.encode())
    return binascii.b2a_hex(encrypted).decode()

## 修改它为从 cookie 直接查询的方式

async def check_cookies(cookies) -> bool:
    api = "https://passport.bilibili.com/x/passport-login/web/cookie/info"
    c = {}
    c["SESSDATA"] = cookies.get("SESSDATA")
    csrf = cookies.get("bili_jct")
    if not c["SESSDATA"] or not csrf:
        return False
    resp = await get(api, cookies=c,params={"csrf":csrf})
    data = resp.json.get("data")
    if data:
        return data["refresh"]
    return False


async def get_refresh_csrf(cookies) -> str:
    """
    获取刷新 Cookies 的 csrf

    Return:
        str: csrf
    """
    cookies = cookies.copy()
    correspond_path = getCorrespondPath()
    api = f"https://www.bilibili.com/correspond/1/{correspond_path}"
    cookies["Domain"] = ".bilibili.com"
    resp = await get(
        api,
        cookies=cookies,
    )
    if resp.status_code == 404:
        raise Exception("correspondPath 过期或错误。")
    elif resp.status_code == 200:
        text = resp.text
        refresh_csrf = re.findall('<div id="1-name">(.+?)</div>', text)[0]
        return refresh_csrf
    elif resp.status_code != 200:
        raise Exception("获取刷新 Cookies 的 csrf 失败。")


async def refresh_cookies(cookies) -> dict:
    """
    刷新 Cookies

    Args:
        credential (Credential): 用户凭证

    Return:
        Credential: 新的用户凭证
    """
    api = "https://passport.bilibili.com/x/passport-login/web/cookie/refresh"
    refresh_csrf = await get_refresh_csrf(cookies)
    data = {
        "csrf": cookies["bili_jct"],
        "refresh_csrf": refresh_csrf,
        "refresh_token": cookies["ac_time_value"],
        "source": "main_web",
    }
    cookies["Domain"] = ".bilibili.com"
    resp = await post(
     api, cookies=cookies, data=data
    )
    if resp.status_code != 200 or resp.json["code"] != 0:
        raise Exception("刷新 Cookies 失败")
    new_credential = dict(
        sessdata=resp.cookies["SESSDATA"],
        bili_jct=resp.cookies["bili_jct"],
        dedeuserid=resp.cookies["DedeUserID"],
        ac_time_value=resp.json["data"]["refresh_token"],
    )
    return new_credential

