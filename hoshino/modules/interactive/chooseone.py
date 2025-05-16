from hoshino import Service, Event, Bot, Message
import random

sv = Service("chooseone")
co = sv.on_command("选择", only_group=False, priority=2)


@co.handle()
async def _(bot: Bot, event: Event):
    msg = str(event.get_message())
    msg = msg.split("还是")
    if len(msg) == 1:
        return
    choices = list(filter(lambda x: len(x) != 0, msg))
    if not choices:
        await co.finish("选项不能全为空！", at_sender=True)
    msgs = ["您的选项是:"]
    idchoices = list(f"{i + 1}. {choice}" for i, choice in enumerate(choices))
    msgs.extend(idchoices)
    if random.randint(0, 1000) <= 76:
        msgs.append("建议您选择: “我全都要”")
    else:
        final = random.choice(choices)
        msgs.append(f"建议您选择: {final}")
    await co.finish(Message("\n".join(msgs)), call_header=True)
