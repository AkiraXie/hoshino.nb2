from hoshino import Service, Matcher, MessageSegment, T_State
from hoshino.permission import SUPERUSER
import os
import random
from pathlib import Path


sv = Service("foods", enable_on_default=False, manage_perm=SUPERUSER)
foods = [
    i for i in Path(os.path.dirname(__file__) + "/images").iterdir() if i.is_file()
]


@sv.on_regex(r"(.{1,9})吃(什么|啥)", priority=3)
async def _(m: Matcher, s: T_State):
    if not foods:
        return
    res = random.choice(foods)
    name = s["_matched_groups"][0]
    with open(res, "rb") as f:
        img = MessageSegment.image(f.read())
    await m.send(f"{name}吃{res.stem}吧! \n" + img, call_header=True)
