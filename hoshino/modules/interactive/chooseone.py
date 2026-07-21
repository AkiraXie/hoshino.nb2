import random

from hoshino.command import UniMessage
from hoshino.service import Service

sv = Service("chooseone")
co = sv.on_command("选择", only_group=False, priority=2)


@co.handle()
async def _(text: str):
    rng = random.SystemRandom()
    msg = text.split("还是")
    if len(msg) == 1:
        return
    choices = list(filter(lambda x: len(x) != 0, msg))
    if not choices:
        await co.finish("选项不能全为空！", at_sender=True)
    msgs = ["您的选项是:"]
    idchoices = list(f"{i + 1}. {choice}" for i, choice in enumerate(choices))
    msgs.extend(idchoices)
    if rng.randint(0, 1000) <= 66:
        msgs.append("建议您选择: “我全都要”")
    else:
        final = rng.randint(0, len(choices) - 1)
        msgs.append(f"建议您选择: {choices[final]}")
    await UniMessage.text("\n".join(msgs)).send()
