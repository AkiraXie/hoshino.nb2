from hoshino import Service, Bot, Event, MessageSegment
from hoshino.util import aiohttpx, FreqLimiter

sv = Service("cloudmusic", visible=False, enable_on_default=False)


async def query_music(name: str) -> int:
    res = await aiohttpx.get(
        "http://music.163.com/api/search/get", params={"type": 1, "s": name}
    )
    data = res.json
    return data["result"]["songs"][0]["id"]


flimit = FreqLimiter(20)


m = sv.on_command("点歌")


@m
async def _(bot: Bot, event: Event):
    uid = event.get_user_id()
    if not flimit.check(uid):
        m.finish("点歌太快了！")
    name = event.get_plaintext()
    await m.send(MessageSegment.music(163, await query_music(name)))
    flimit.start_cd(uid)
