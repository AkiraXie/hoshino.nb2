import asyncio
import random
import re
from pathlib import Path

from hoshino.command import UniMessage
from hoshino.core.permission import SUPERUSER
from hoshino.platform.depends import PlainText
from hoshino.service import Service

sv = Service("foods", enable_on_default=False, manage_perm=SUPERUSER)
_images_dir = Path(__file__).resolve().parent / "images"
foods = [p for p in _images_dir.iterdir() if p.is_file()] if _images_dir.is_dir() else []


food = sv.on_regex(r"(.{0,9})吃(什么|啥)", priority=3)


@food.handle()
async def _(text: str = PlainText()):
    rng = random.SystemRandom()
    if not foods:
        return
    res = rng.choice(foods)
    match = re.match(r"(.{0,9})吃(?:什么|啥)", text)
    if match is None:
        return
    name = match.group(1)
    # 同步读文件放到线程池执行，避免阻塞事件循环
    img = await asyncio.to_thread(res.read_bytes)
    await food.send(
        UniMessage.text(f"{name}吃{res.stem}吧! \n") + UniMessage.image(raw=img),
        call_header=True,
    )
