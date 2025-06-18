from hoshino.util import (
    sucmd,
    finish,
    save_cookies,
    send,
    check_all_cookies,
    check_cookies,
)
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
    await send(f"保存 {name} cookies 成功")


@sucmd("check_cookies", aliases={"检查cookies", "ckck"}, only_to_me=True)
async def check_cookies_cmd(
    event: MessageEvent,
):
    msgs = event.get_plaintext()
    if len(msgs) == 0 or msgs == "all":
        cookies = check_all_cookies()
    else:
        cookies = {}
        name = msgs
        cookies[name] = check_cookies(name)
    if not cookies:
        await send("没有可用的cookies")
    else:
        await send(f"可用的cookies: {', '.join(cookies)}")
