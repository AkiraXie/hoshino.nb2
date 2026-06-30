import base64
from hoshino.service import Service
from hoshino.types import Bot, Event
from hoshino.platform import get_plaintext

sv = Service("b64", enable_on_default=False)


@sv.on_command("b64加密", only_group=False)
async def _(bot: Bot, event: Event):
    res = base64.b64encode(get_plaintext(event).encode()).decode("utf8")
    await bot.send(event, res)


@sv.on_command("b64", aliases={"b64解密"}, only_group=False)
async def _(bot: Bot, event: Event):
    res = base64.b64decode(get_plaintext(event)).decode("utf8")
    await bot.send(event, res)
