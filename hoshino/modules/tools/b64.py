import base64
from hoshino.service import Service
from hoshino.platform import Alconna, Args, UniMessage

sv = Service("b64", enable_on_default=False)

encrypt = sv.on_alconna(Alconna("b64加密", Args["text", str]), only_group=False)
decrypt = sv.on_alconna(Alconna("b64", Args["text", str]), aliases=("b64解密",), only_group=False)


@encrypt.handle()
async def _(text: str):
    res = base64.b64encode(text.encode()).decode("utf8")
    await UniMessage.text(res).send()


@decrypt.handle()
async def _(text: str):
    res = base64.b64decode(text).decode("utf8")
    await UniMessage.text(res).send()
