from hoshino import Service, Event, MessageSegment
from hoshino.util import Cooldown, aiohttpx

sv = Service("cloudmusic", visible=False, enable_on_default=False)


async def query_music(name: str) -> int:
    res = await aiohttpx.get(
        "http://music.163.com/api/search/get", params={"type": 1, "s": name}
    )
    data = res.json
    return data["result"]["songs"][0]["id"]




m = sv.on_command("点歌")


@m
async def _(event: Event, _=Cooldown(30,"点歌太快了！")):
    name = event.get_plaintext()
    await m.send(MessageSegment.music(163, await query_music(name)))

