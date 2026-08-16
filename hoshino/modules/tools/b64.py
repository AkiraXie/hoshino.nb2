import base64
import binascii

from hoshino.command import UniMessage
from hoshino.platform.depends import ParamText
from hoshino.service import Service

sv = Service("b64", enable_on_default=False)

encrypt = sv.on_command("b64加密", only_group=False)
decrypt = sv.on_command("b64", aliases=("b64解密",), only_group=False, compact=False)


@encrypt.handle()
async def _(text: str = ParamText()):
    res = base64.b64encode(text.encode()).decode("utf8")
    await UniMessage.text(res).send()


@decrypt.handle()
async def _(text: str = ParamText()):
    try:
        res = base64.b64decode(text).decode("utf8")
    except (binascii.Error, UnicodeDecodeError):
        await decrypt.finish("解码失败，请检查输入")
    await UniMessage.text(res).send()
