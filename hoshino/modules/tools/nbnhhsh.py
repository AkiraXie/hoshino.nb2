from hoshino.command import AlcResult, UniMessage
from hoshino.service import Service
from hoshino.util import aiohttpx

sv = Service("nbnhhsh")
nbn = sv.on_regex(r"^[\?\？]{1,2} ?([a-z0-9]+)$", only_group=False)


@nbn.handle()
async def _(result: AlcResult):
    match_obj = result.result.header_match.result
    text = match_obj.group(1)
    resp = await aiohttpx.post(
        "https://lab.magiconch.com/api/nbnhhsh/guess", json={"text": text}
    )
    j = resp.json
    if len(j) == 0:
        await UniMessage.text(f"{text}: 没有结果").send()
        return
    res = j[0]
    name = res.get("name")
    trans = res.get("trans", ["没有结果"])
    msg = "{}: {}".format(
        name,
        " ".join(trans),
    )
    await UniMessage.text(msg).send()
