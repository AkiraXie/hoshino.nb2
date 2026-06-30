from html import unescape

from hoshino.util import sucmd
from hoshino.service import Service
from hoshino.permission import SUPERUSER
from hoshino.platform import Alconna, MsgId, UniMessage, UniMsg


async def handle_echo(msg: UniMsg):
    await UniMessage.text(unescape(str(msg))).send()


async def handle_reply(msg: UniMsg, message_id: MsgId):
    await UniMessage.text(unescape(str(msg))).send(reply_to=message_id)


echo = sucmd("echo")
echo.handle()(handle_echo)
sv = Service("say", manage_perm=SUPERUSER, enable_on_default=False)
sv.on_alconna(Alconna("say"), only_group=False)(handle_echo)
