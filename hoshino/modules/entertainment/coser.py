from hoshino.service import Service
from hoshino.platform import Alconna, UniMessage
from hoshino.util import Cooldown, aiohttpx

sv = Service("coser", visible=False, enable_on_default=False)


m = sv.on_alconna(Alconna("coser"), only_to_me=True)


@m
async def _(_=Cooldown(10, "冲太快了")):
    res = await aiohttpx.get("https://api.suyanw.cn/api/cos.php?type=json")
    data = res.json["text"]
    await UniMessage.image(url=data).send()
