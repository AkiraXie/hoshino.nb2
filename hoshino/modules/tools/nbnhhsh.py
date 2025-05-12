from nonebot.typing import T_State
from hoshino import Service, aiohttpx

sv = Service("nbnhhsh")
nbn = sv.on_regex(r"^[\?\？]{1,2} ?([a-z0-9]+)$", only_group=False)


@nbn.handle()
async def _(state: T_State):
    text = state["match"].group(1)
    resp = await aiohttpx.post(
        "https://lab.magiconch.com/api/nbnhhsh/guess", json={"text": text}
    )
    j = resp.json
    if len(j) == 0:
        await nbn.finish(f"{text}: 没有结果")
    res = j[0]
    name = res.get("name")
    trans = res.get("trans", ["没有结果"])
    msg = "{}: {}".format(
        name,
        " ".join(trans),
    )
    await nbn.finish(msg)
