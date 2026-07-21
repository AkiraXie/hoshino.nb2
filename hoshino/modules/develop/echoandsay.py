from hoshino.command import MsgId, UniMessage
from hoshino.core.permission import SUPERUSER
from hoshino.service import Service

sv = Service("echoandsay", manage_perm=SUPERUSER, enable_on_default=True)

echo = sv.on_command("echo")
say = sv.on_command("say")


@echo.handle()
async def _(text: str):
    await UniMessage.text(text).send()


@say.handle()
async def _(text: str, message_id: MsgId):
    await UniMessage.text(text).send(reply_to=message_id)
