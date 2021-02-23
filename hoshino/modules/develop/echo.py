from hoshino import sucmd, Bot, Event, Service, permission,Message
from nonebot.adapters.cqhttp.utils import unescape

async def handle_echo(bot: Bot, event: Event):
    await bot.send(event, Message(unescape(str(event.get_message()))))

sucmd('echo').handle()(handle_echo)
sv = Service('say', manage_perm=permission.SUPERUSER, enable_on_default=False)
sv.on_command('say')(handle_echo)
