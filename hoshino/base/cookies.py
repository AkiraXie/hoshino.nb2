from hoshino.util import sucmd, finish, save_cookies, send
from hoshino.event import MessageEvent


@sucmd(
    "save_cookies", aliases={"保存cookies", "addck", "添加cookies"}, only_to_me=True
).handle()
async def save_cookies_cmd(
    event: MessageEvent,
):
    msgs = event.get_plaintext().split(None, 1)
    name = msgs[0]
    cookies = msgs[1]
    if not name:
        await finish("请提供cookie名称")
    if not cookies:
        await finish("请提供cookie")

    save_cookies(name, cookies)
    await send(f"保存 {name} cookies成功")
