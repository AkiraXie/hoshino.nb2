from hoshino import Service, Matcher, MessageSegment, T_State
from hoshino.permission import SUPERUSER
import os
import random
from pathlib import Path
sv = Service('foods', enable_on_default=False,manage_perm=SUPERUSER)
foods = [i for i in Path(os.path.dirname(__file__)+'/images').iterdir()]
@sv.on_regex(r'(.{1,6})吃(什么|啥)')
async def _(m:Matcher,s:T_State):
    res = random.choice(foods)
    name = s["_matched_groups"][0]
    img = MessageSegment.image(res)
    await m.send(f'{name}吃{res.stem}吧！'+img,call_header=True)