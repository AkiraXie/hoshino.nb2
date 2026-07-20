import random

from hoshino.command import AlcResult, UniMessage
from hoshino.service import Service

sv = Service("dice", visible=False)
d = sv.on_regex(r".r(\d{1,2})d(\d{1,3})([+-]\d{1,3})?")


@d.handle()
async def _(result: AlcResult):
    match_obj = result.result.header_match.result
    rd = random.SystemRandom()
    num = match_obj.group(1)
    mx = match_obj.group(2)
    offset = match_obj.group(3)
    res = []
    rs = "本次掷骰结果为: "
    for i in range(int(num)):
        c = rd.randint(1, int(mx))
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
