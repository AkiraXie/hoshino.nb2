import random
from json import loads
from urllib.parse import quote

from hoshino.command import UniMessage
from hoshino.core.schedule import scheduled_job
from hoshino.platform.depends import ParamText
from hoshino.service import Service
from hoshino.util import aiohttpx

sv = Service("bihua", visible=False, enable_on_default=False)

_bihuas: dict[str, str] = {}
# 兼容性别名：nb-tests 直接替换模块属性 `bihuas` 注入测试数据，
# handler 经 `bihuas` 读取；生产环境中两者指向同一对象。
bihuas = _bihuas

configurl = "https://bihua.bleatingsheep.org/meme-data.json"
prefix = "https://bihua.bleatingsheep.org/meme/"
m = sv.on_command("bihua", aliases=("b话", "壁画"), block=True)
r = sv.on_command("随机壁画", aliases=("随机bihua", "随机b话"), block=True)
s = sv.on_command("搜索壁画", aliases=("searchbihua", "搜索b话"), block=True)


def _search_bihua(keywords: list[str]) -> list[str]:
    """返回与全部关键词（不区分大小写）匹配的壁画名。"""
    word_queries = {word.lower() for word in keywords}
    return [bihua for bihua in bihuas if all(word in bihua.lower() for word in word_queries)]


@scheduled_job("interval", seconds=240, id="bihua_config", jitter=5)
async def fetch_bihua_config():
    try:
        resp = await aiohttpx.get(configurl, timeout=10)
        if resp.ok:
            images = {}
            for image in loads(resp.text).get("images", []):
                line: str = image.get("path", "")
                line = line.removeprefix("meme/")
                for ext in [".jpg", ".png", ".jpeg"]:
                    if line.endswith(ext):
                        line = line[: -len(ext)]
                        images[line] = ext
                        break
            _bihuas.clear()
            _bihuas.update(images)
    except Exception:
        sv.logger.exception(f"Error fetching bihua config from {configurl}", exception=True)


@r.handle()
async def _():
    ra = random.SystemRandom()
    if not bihuas:
        await r.finish()
    ls = list(bihuas.keys())
    matching_bihua = ra.choice(ls)
    link = prefix + matching_bihua
    link2 = quote(link, safe=":/") + bihuas[matching_bihua]
    await UniMessage.image(url=link2).send()


@m.handle()
async def _(text: str = ParamText()):
    if not text:
        await m.finish()
    keywords = text.split()
    if not keywords:
        await m.finish()
    matching_bihuas = _search_bihua(keywords)
    if not matching_bihuas:
        await fetch_bihua_config()
        matching_bihuas = _search_bihua(keywords)
    if not matching_bihuas:
        await m.finish()
    ra = random.SystemRandom()
    matching_bihua = ra.choice(matching_bihuas)
    link = prefix + matching_bihua
    link2 = quote(link, safe=":/") + bihuas[matching_bihua]
    await UniMessage.image(url=link2).send()


@s.handle()
async def _(text: str = ParamText()):
    if not text:
        await s.finish()
    keywords = text.split()
    if not keywords:
        await s.finish()
    matching_bihuas = _search_bihua(keywords)
    if not matching_bihuas:
        await fetch_bihua_config()
        matching_bihuas = _search_bihua(keywords)
    if not matching_bihuas:
        await s.finish()
    await s.send(f"找到壁画：\n-----------\n{'\n'.join(matching_bihuas)}")
