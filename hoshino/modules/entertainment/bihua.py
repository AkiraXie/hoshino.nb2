from hoshino import Service, Event, MessageSegment
from hoshino.util import Cooldown, aiohttpx
from urllib.parse import quote
sv = Service("bihua", visible=False, enable_on_default=False)




m = sv.on_command("bihua",aliases=("b话"))


@m.handle()
async def _( event : Event):
    msg = event.get_plaintext()
    if not msg:
        await m.finish()
    link = "https://bihua.bleatingsheep.org/meme/{}.jpg".format(msg)
    link = quote(link, safe=":/")
    link2 = "https://bihua.bleatingsheep.org/meme/{}.png".format(msg)
    link2 = quote(link2, safe=":/")
    res = await aiohttpx.get(link,follow_redirects=True)
    if not res.ok:
        res = await aiohttpx.get(link2,follow_redirects=True)
        if not res.ok:
            await m.finish()
    data = res.content
    if not data:
        await m.finish()
    await m.send(MessageSegment.image(data))
 