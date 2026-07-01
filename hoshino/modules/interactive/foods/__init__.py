from hoshino.service import Service
from hoshino.command import AlconnaResult, UniMessage
from hoshino.core.permission import SUPERUSER
import os
import random
from pathlib import Path

sv = Service("foods", enable_on_default=False, manage_perm=SUPERUSER)
foods = [
    i for i in Path(os.path.dirname(__file__) + "/images").iterdir() if i.is_file()
]


food = sv.on_regex(r"(.{1,9})吃(什么|啥)", priority=3)


@food.handle()
async def _(result: AlconnaResult):
    rng = random.SystemRandom()
    if not foods:
        return
    res = rng.choice(foods)
    name = result.result.header_match.result.group(1)
    with open(res, "rb") as f:
        img = f.read()
    await (UniMessage.text(f"{name}吃{res.stem}吧! \n") + UniMessage.image(raw=img)).send(
        call_header=True
    )
