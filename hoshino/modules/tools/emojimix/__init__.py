## Thanks to github.com/FloatTech/ZeroBot-Plugin/plugin/emojimix

from hoshino.service import Service
from nonebot.matcher import Matcher
from nonebot.typing import T_State
from hoshino.util import aiohttpx
from hoshino.permission import SUPERUSER
from nonebot.adapters import Event
from hoshino.platform import UniMessage, get_event_message, get_event_value, get_plaintext
from .data import emojis, qqface

sv = Service("emojimix", visible=False, enable_on_default=False)

bed = "https://www.gstatic.com/android/keyboard/emojikitchen/%s/u%s/u%s_u%s.png"


def multichar_ord(s: str) -> str:
    return "-".join(f"{ord(c):x}" for c in s)


def char_ord(s: str) -> str:
    return f"{ord(s):x}"


async def emojimatch(event: Event, state: T_State):
    msg = get_event_message(event, [])
    res = []
    if len(msg) > 2:
        return False
    if len(msg) == 1:
        text = get_plaintext(event)
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


@sv.on_command("testemoji", permission=SUPERUSER)
async def _(matcher: Matcher, event: Event):
    raw_message = get_event_value(event, "raw_message", "")
    msg = []
    msg.append(str(get_event_message(event, "")))
    msg.append(raw_message)
    msg.append(str([ord(i) for i in get_plaintext(event)]))
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
