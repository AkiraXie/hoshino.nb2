from hoshino.command import MsgId, UniMessage
from hoshino.core.permission import SUPERUSER
from hoshino.platform.depends import ParamText
from hoshino.service import Service

sv = Service("echoandsay", manage_perm=SUPERUSER, enable_on_default=True)

echo = sv.on_command(name="echo",permission=SUPERUSER)
say = sv.on_command(name="say")


@echo.handle()
async def _(text: str = ParamText()):
    if not text:
        return
    await UniMessage.text(text).send()


@say.handle()
async def _(message_id: MsgId, text: str = ParamText()):
    if not text:
        return
    await UniMessage.text(text).send(reply_to=message_id)
