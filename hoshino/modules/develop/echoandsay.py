from html import unescape

from hoshino.service import Service
from hoshino.permission import SUPERUSER
from hoshino.platform import Alconna, Args, MsgId, UniMessage, UniMsg

sv = Service("echoandsay", manage_perm=SUPERUSER, enable_on_default=True)


@sv.on_alconna(Alconna("echo", Args["text", str]))
async def _(msg: UniMsg):
    await UniMessage.text(unescape(str(msg))).send()


@sv.on_alconna(Alconna("say", Args["text", str]))
async def _(msg: UniMsg, message_id: MsgId):
    await UniMessage.text(unescape(str(msg))).send(reply_to=message_id)
