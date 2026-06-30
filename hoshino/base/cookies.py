from hoshino.util import (
    sucmd,
    finish,
    save_cookies,
    send,
    check_all_cookies,
    check_cookies,
    delete_cookies,
)
from hoshino.platform import PlainText
from simplejson import loads


@sucmd(
    "save_cookies", aliases={"保存cookies", "addck", "添加cookies"}, only_to_me=True
).handle()
async def save_cookies_cmd(msg: str = PlainText()):
    msgs = msg.split(None, 1)
    if len(msgs) < 2:
        await finish("请提供cookie名称和cookie内容")
        return
    name = msgs[0]
    cookies = msgs[1]
    try:
        cookies = loads(cookies)
    except Exception:
        pass
    if not name:
        await finish("请提供cookie名称")
    if not cookies:
        await finish("请提供cookie")

    await save_cookies(name, cookies)
    await send(f"保存 {name} cookies 成功")


@sucmd("check_cookies", aliases={"检查cookies", "ckck"}, only_to_me=True).handle()
async def check_cookies_cmd(msg: str = PlainText()):
    msgs = msg.strip()
    if len(msgs) == 0 or msgs == "all":
        cookies = check_all_cookies()
    else:
        cookies = {}
        name = msgs
        if v := check_cookies(name):
            cookies[name] = v
    if not cookies:
        await send("没有可用的cookies")
    else:
        await send(f"可用的cookies: {', '.join(cookies)}")


@sucmd(
    "del_cookies", aliases={"删除cookies", "delck", "删除ck"}, only_to_me=True
).handle()
async def del_ck_cmd(name: str = PlainText()):
    if not name:
        await finish("请提供cookie名称")

    if name == "all":
        cookies = check_all_cookies()
        if not cookies:
            await send("没有可删除的cookies")
            return
        for k in list(cookies):
            try:
                await delete_cookies(k)
            except Exception:
                pass
        await send("删除所有cookies 成功")
        return

    if not check_cookies(name):
        await finish("没有可删除的cookies")
    try:
        await delete_cookies(name)
        await send(f"删除 {name} cookies 成功")
    except Exception as e:
        await send(f"删除失败: {e}")
