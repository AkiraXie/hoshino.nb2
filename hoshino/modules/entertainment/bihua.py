from hoshino import Service, Event, MessageSegment, scheduled_job, on_startup
from hoshino.util import aiohttpx
from urllib.parse import quote
import random

sv = Service("bihua", visible=False, enable_on_default=False)

bihuas = dict()
configurl = "https://bihua.bleatingsheep.org/static/scripts/config.js"
prefix = "https://bihua.bleatingsheep.org/meme/"
m = sv.on_command("bihua", aliases=("b话", "壁画"), block=True)
r = sv.on_command("随机壁画", aliases=("随机bihua", "随机b话"), block=True)


@scheduled_job("interval", seconds=120, id="bihua_config", jitter=5)
@on_startup
async def fetch_bihua_config():
    try:
        global bihuas
        bi_copy = bihuas.copy()
        resp = await aiohttpx.get(configurl, timeout=10, follow_redirects=True)
        if resp.ok:
            content = resp.text
            lines = content.splitlines()
            content_lines = lines[2:-3]
            for line in content_lines:
                line = line.strip().removeprefix('"meme/').removesuffix('",')
                for ext in [".jpg", ".png", ".jpeg"]:
                    if line.endswith(ext):
                        line = line[: -len(ext)]
                        bi_copy[line] = ext
                        break
        bihuas = bi_copy
    except Exception:
        sv.logger.error(f"Error fetching config: {resp.status_code}")


@r.handle()
async def _():
    ra = random.SystemRandom()
    if not bihuas:
        await r.finish()
    ls = list(bihuas.keys())
    matching_bihua = ra.choice(ls)
    link = prefix + matching_bihua
    link2 = quote(link, safe=":/") + bihuas[matching_bihua]
    await r.send(MessageSegment.image(link2))


@m.handle()
async def _(event: Event):
    msg = event.get_plaintext()
    if not msg:
        await m.finish()
    keywords = msg.split()
    if not keywords:
        await m.finish()
    word_queries = set(keywords)
    matching_bihuas = [
        bihua
        for bihua in bihuas
        if all(word.lower() in bihua.lower() for word in word_queries)
    ]
    if not matching_bihuas:
        await m.finish()
    ra = random.SystemRandom()
    matching_bihua = ra.choice(matching_bihuas)
    link = prefix + matching_bihua
    link2 = quote(link, safe=":/") + bihuas[matching_bihua]
    await m.send(MessageSegment.image(link2))
