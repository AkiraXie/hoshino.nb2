from hoshino import Service, Event, MessageSegment,scheduled_job
from hoshino.util import Cooldown, aiohttpx
from urllib.parse import quote
sv = Service("bihua", visible=False, enable_on_default=False)

bihuas = set()
configurl = 'https://github.com/b11p/bihua/blob/main/static/scripts/config.js'
prefix = "https://bihua.bleatingsheep.org/"
m = sv.on_command("bihua",aliases=("b话"))

@scheduled_job("interval", seconds=120, id="bihua_config",jitter=5)
async def fetch_bihua_config():
    try:
        bihuas.clear()
        resp = await aiohttpx.get(configurl, timeout=10)
        if resp.ok:
            content = resp.text
            lines = content.splitlines()
            content_lines = lines[2:-3]
            for line in content_lines:
                line = line.strip().removeprefix('"').removesuffix('",')
                bihuas.add(line)
    except Exception :   
        sv.logger.error(f"Error fetching config: {resp.status_code}")

@m.handle()
async def _( event : Event):
    msg = event.get_plaintext()
    if not msg:
        await m.finish()
    keywords= msg.split()
    if not keywords:
        await m.finish()
    word_queries = set(keywords)
    matching_bihua = next((bihua for bihua in bihuas if all(word in bihua for word in word_queries)), None)
    if not matching_bihua:
        await m.finish()
    link = prefix + matching_bihua
    link2 = quote(link, safe=":/")
    await m.send(MessageSegment.image(link2))
 