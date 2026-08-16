from hoshino.command import UniMessage
from hoshino.platform.depends import PlainText
from hoshino.service import Service
from hoshino.util import aiohttpx

sv = Service("nbnhhsh")
nbn = sv.on_regex(r"^[\?\？]{1,2} ?([a-z0-9]+)$", only_group=False)


@nbn.handle()
async def _(text: str = PlainText()):
    text = text.lstrip("?？").strip()
    if not text:
        return
    resp = await aiohttpx.post("https://lab.magiconch.com/api/nbnhhsh/guess", json={"text": text})
    j = resp.json
    if len(j) == 0:
        await UniMessage.text(f"{text}: 没有结果").send()
        return
    res = j[0]
    name = res.get("name")
    trans = res.get("trans", ["没有结果"])
    msg = f"{name}: {' '.join(trans)}"
    await UniMessage.text(msg).send()
