"""
Author: AkiraXie
Date: 2021-01-31 03:06:03
LastEditors: AkiraXie
LastEditTime: 2022-02-16 22:42:30
Description: 
Github: http://github.com/AkiraXie/
"""

from hoshino import Service, Message, Matcher
from hoshino.typing import T_State
from hoshino.util import Cooldown
from hoshino.modules.priconne.chara import Chara

sv = Service("whois")

STARDIC = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6}





whois = sv.on_regex(r"^谁是(.{1,20})$", only_group=False)

@whois.handle()
async def handle_whois(matcher:Matcher, state: T_State,_=Cooldown(prompt="您的查询将在10秒后可用")):
    match = state["match"]
    name = match.group(1)
    if name.isdigit():
        chara = Chara.fromid(int(name), star=0)
    else:
        chara = Chara.fromname(name, star=0)
    if chara.id == Chara.UNKNOWN:
        msg = f'兰德索尔似乎没有叫"{name}"的人'
        await matcher.finish(msg, call_header=True)
    msg = f"{chara.name}\n{chara.icon.CQcode}"
    await matcher.send(Message(msg), call_header=True)

async def handle_lookcard(matcher:Matcher, state: T_State, _=Cooldown(prompt="您的查询将在10秒后可用")):
    match = state["match"]
    name = match.group(2)
    star = (
        match.group(1)[0]
        if match.group(1)
        else match.group(3)[0]
        if match.group(3)
        else 0
    )
    star = STARDIC.get(star, star)
    chara = Chara.fromname(name, star=int(star))
    msg = chara.card
    await matcher.send(Message(msg), call_header=True)


lookcard = sv.on_regex(
    r"^([1-6一二三四五六][xX星])?\s?(.*?)([1-6一二三四五六][xX星])?(立绘|卡面)$",
    only_group=False,
    handlers=[handle_lookcard],
)


look_en_jp_name = sv.on_regex(r"^(.{1,20})(日|英)[语文]名$", only_group=False)


@look_en_jp_name
async def _(matcher:Matcher, state: T_State,_=Cooldown(prompt="您的查询将在10秒后可用")):
    match = state["match"]
    name = match.group(1)
    region = match.group(2)
    if name.isdigit():
        chara = Chara.fromid(int(name), star=0)
    else:
        chara = Chara.fromname(name, star=0)
    if region == "英":
        msg = f"{chara.enname}\n{chara.icon.CQcode}"
    else:
        msg = f"{chara.jpname}\n{chara.icon.CQcode}"
    await matcher.send(Message(msg), call_header=True)
