'''
Author: AkiraXie
Date: 2022-01-06 22:13:45
LastEditors: AkiraXie
LastEditTime: 2022-02-09 01:47:47
Description: 
Github: http://github.com/AkiraXie/
'''
from hoshino.schedule import scheduled_job
from hoshino import Service, Bot, Event, Message, MessageSegment, sucmd, R
from hoshino.util.aiohttpx import get
from hoshino.typing import List
import os
cookies = {"SESSDATA": "da2da747%2C1650364546%2Cf79d1%2Aa1"}
vjson = os.path.abspath(os.path.dirname(__file__))+"/vtbs.json"
sv = Service('chengfenji', enable_on_default=False)
cfj = sv.on_command("查成分", aliases={"成分姬"})

async def get_user_follow(uid:str) -> List[str]:
    mids = []
    for i in range(1,6):
        params = {'vmid': uid, 'pn': i}
        try:
            r = await get('https://api.bilibili.com/x/relation/followings', cookies=cookies,params=params)
            data =  r.json
            for i in data['data']['list']:
                mids.append(str(i['mid']))
        except Exception as e:
            sv.logger.error(e)
            continue 
    return mids
        

@cfj
async def _(bot: Bot, event: Event):
    uid = event.get_plaintext()
    if not uid.isdigit():
        await cfj.finish("请输入纯数字uid")
    params1 = {'mid': uid, "photo": "false"}
    res1 = await get('http://api.bilibili.com/x/web-interface/card', params=params1, cookies=cookies)
    j1 = res1.json
    if j1['code'] != 0:
        await cfj.finish("uid无效")
    name = j1['data']["card"]['name']
    face = j1['data']["card"]['face']
    face = MessageSegment.image(face)
    mids = await get_user_follow(uid)
    from json import load
    with open(vjson, encoding="utf8") as f:
        dic = load(f)
    vtb_set = set(dic.keys())
    res_set = set(mids) & vtb_set
    l = len(res_set)
    msgs = [f"{name}\n{face}", f"关注的vup有{l}个: "]
    for i in res_set:
        name = dic[i]["uname"]
        msg = f"{name}"
        msgs.append(msg)
    await cfj.finish(Message("\n".join(msgs)))

su = sucmd("更新成分姬", aliases={"更新v", "updatev"})

@su.handle()
async def _(bot: Bot, event: Event):
    try:
        await up()
    except Exception as e:
        await su.finish(f"更新成分姬失败\n{e}")
    await su.finish("更新成分姬成功")

@scheduled_job("cron", hour="*/6", minute="2")
async def up():
    from json import dump
    res2 = await get('https://api.vtbs.moe/v1/info')
    vtbs = res2.json
    vtb_dict = {i["mid"]: {"uname": i["uname"], "face": i["face"]}
                for i in vtbs}
    with open(vjson, "w", encoding="utf8") as f:
        dump(vtb_dict, f, ensure_ascii=False, indent=4)
    