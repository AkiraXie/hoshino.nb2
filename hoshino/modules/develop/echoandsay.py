from hoshino.util import sucmd
from hoshino.service import Service
from hoshino.permission import SUPERUSER
from hoshino.types import Bot, Event, Message, MessageSegment
from nonebot.adapters.onebot.v11.utils import unescape


async def handle_echo(bot: Bot, event: Event):
    await bot.send(event, Message(unescape(str(event.get_message()))))


async def handle_reply(bot: Bot, event: Event):
    rep = MessageSegment.reply(event.message_id)
    await bot.send(event, Message(rep + unescape(str(event.get_message()))))


sucmd("echo").handle()(handle_echo)
sv = Service("say", manage_perm=SUPERUSER, enable_on_default=False)
sv.on_command("say")(handle_echo)
