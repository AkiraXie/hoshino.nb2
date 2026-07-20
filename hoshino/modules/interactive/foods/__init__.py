import os
import random
import re
from pathlib import Path

from hoshino.command import AlcResult, UniMessage
from hoshino.core.permission import SUPERUSER
from hoshino.platform.depends import PlainText
from hoshino.service import Service

sv = Service("foods", enable_on_default=False, manage_perm=SUPERUSER)
foods = [
    i for i in Path(os.path.dirname(__file__) + "/images").iterdir() if i.is_file()
]


food = sv.on_regex(r"(.{0,9})吃(什么|啥)", priority=3)


@food.handle()
async def _(result: AlcResult, text: str = PlainText()):
    rng = random.SystemRandom()
    if not foods:
        return
    res = rng.choice(foods)
    match = re.match(r"(.{0,9})吃(?:什么|啥)", text)
    if match is None:
        return
    name = match.group(1)
    with open(res, "rb") as f:
        img = f.read()
    await food.send(
        UniMessage.text(f"{name}吃{res.stem}吧! \n") + UniMessage.image(raw=img),
        call_header=True,
    )
