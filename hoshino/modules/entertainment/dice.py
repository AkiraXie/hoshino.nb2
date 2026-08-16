import random
import re

from nonebot.params import RegexMatched

from hoshino.command import UniMessage
from hoshino.service import Service

sv = Service("dice", visible=False)
d = sv.on_regex(r"\.r(\d{1,2})d(\d{1,3})([+-]\d{1,3})?")


@d.handle()
async def _(match_obj: re.Match[str] = RegexMatched()):
    rd = random.SystemRandom()
    num = int(match_obj.group(1))
    mx = int(match_obj.group(2))
    offset = match_obj.group(3)
    if num < 1 or mx < 1:
        await d.finish("骰子数量和面数至少为 1")
    res = []
    rs = "本次掷骰结果为: "
    for _ in range(num):
        c = rd.randint(1, mx)
        res.append(c)
    su = sum(res)
    rs += "+".join(str(i) for i in res)
    if offset is not None:
        off = str(offset)
        if offset[0] == "+":
            su += int(off[1:])
        if offset[0] == "-":
            su -= int(off[1:])
        rs += off + "(offset)"
    if len(res) != 1 or offset is not None:
        rs += "=" + str(su)
    await UniMessage.text(rs).send()
