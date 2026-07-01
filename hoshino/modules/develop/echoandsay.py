from html import unescape

from hoshino.service import Service
from hoshino.core.permission import SUPERUSER
from hoshino.command import Alconna, Args, MsgId, UniMessage, UniMsg

sv = Service("echoandsay", manage_perm=SUPERUSER, enable_on_default=True)

echo = sv.on_alconna(Alconna("echo", Args["text", str]))
say = sv.on_alconna(Alconna("say", Args["text", str]))


@echo.handle()
async def _(msg: UniMsg):
    await UniMessage.text(unescape(str(msg))).send()


@say.handle()
async def _(msg: UniMsg, message_id: MsgId):
    await UniMessage.text(unescape(str(msg))).send(reply_to=message_id)
