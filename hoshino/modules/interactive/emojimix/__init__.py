## Thanks to github.com/FloatTech/ZeroBot-Plugin/plugin/emojimix

from nonebot.matcher import Matcher
from nonebot.typing import T_State

from hoshino.command import UniMessage
from hoshino.core.permission import SUPERUSER
from hoshino.platform.depends import EventMessage, ParamText, PlainText, RawMessage
from hoshino.service import Service
from hoshino.util import aiohttpx

from .data import emojis, qqface

sv = Service("emojimix", visible=False, enable_on_default=False)

bed = "https://www.gstatic.com/android/keyboard/emojikitchen/%s/u%s/u%s_u%s.png"
testemoji = sv.on_command("testemoji", permission=SUPERUSER)


def multichar_ord(s: str) -> str:
    return "-".join(f"{ord(c):x}" for c in s)


def char_ord(s: str) -> str:
    return f"{ord(s):x}"


async def emojimatch(
    state: T_State,
    msg=EventMessage([]),
    text: str = PlainText(),
):
    res = []
    if len(msg) > 2:
        return False
    if len(msg) == 1:
        lt = len(text)
        if lt > 4:
            return False
        elif lt <= 1:
            return False
        elif lt == 2:
            for i in text:
                u = char_ord(i)
                if d := emojis.get(u):
                    res.append((u, d))
        else:
            s = multichar_ord(text).split("fe0f-", 1)
            s[0] = s[0] + "fe0f"
            for u in s:
                if d := emojis.get(u):
                    res.append((u, d))
    else:
        for ms in msg:
            if ms.is_text() and len(i := str(ms)) <= 2:
                u = multichar_ord(i)
                if d := emojis.get(u):
                    res.append((u, d))
            if ms.type == "face":
                e = qqface.get(int(ms.data["id"]))
                if not e:
                    continue
                u = f"{e:x}"
                d = emojis.get(u)
                if d:
                    res.append((u, d))
    if len(res) == 2:
        state["emojimix"] = res
        return True
    else:
        return False


@testemoji.handle()
async def _(
    matcher: Matcher,
    raw_message: str = RawMessage(),
    event_message=EventMessage(""),
    text: str = ParamText(),
):
    msg = []
    msg.append(str(event_message))
    msg.append(raw_message)
    msg.append(str([ord(i) for i in text]))
    msg.append(str([ord(i) for i in raw_message]))
    await matcher.send("\n".join(msg))


@sv.on_message(rule=emojimatch)
async def _(matcher: Matcher, state: T_State):
    res = state["emojimix"]
    r1, d1 = res[0]
    r2, d2 = res[1]
    r1 = r1.replace("fe0f", "ufe0f")
    r2 = r2.replace("fe0f", "ufe0f")
    # left
    url = bed % (d1, r1, r1, r2)
    resp = await aiohttpx.head(url)
    if resp.ok:
        await UniMessage.image(url=url).send()
        await matcher.finish()
    # right
    url = bed % (d2, r2, r2, r1)
    resp = await aiohttpx.head(url)
    if resp.ok:
        await UniMessage.image(url=url).send()
        await matcher.finish()
