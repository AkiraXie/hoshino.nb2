'''
Author: AkiraXie
Date: 2022-03-08 01:26:38
LastEditors: AkiraXie
LastEditTime: 2022-03-11 04:43:23
Description: 
Github: http://github.com/AkiraXie/
'''

## Thanks to github.com/FloatTech/ZeroBot-Plugin/plugin/emojimix

from hoshino import Service, T_State,aiohttpx,Matcher,MessageSegment,SUPERUSER
from hoshino.event import MessageEvent
from .data import emojis, qqface

sv = Service("emojimix",visible=False,enable_on_default=False)

bed = "https://www.gstatic.com/android/keyboard/emojikitchen/%s/u%s/u%s_u%s.png"
multichar_ord = lambda s: '-'.join(map(lambda c: f"{ord(c):x}", s))
char_ord = lambda s: f"{ord(s):x}"
async def emojimatch(event: MessageEvent, state: T_State):
    msg = event.get_message()
    res = []
    if len(msg)>2:
        return False
    if len(msg)==1:
        text = event.get_plaintext()
        lt = len(text)
        if lt>4:
            return False
        elif lt<=1:
            return False
        elif lt==2:
            for i in text:
                u = char_ord(i)
                if d:=emojis.get(u):
                    res.append((u,d))
        else:
            s = multichar_ord(text).split("fe0f-",1)
            s[0] = s[0]+"fe0f"
            for u in s:
                if d:=emojis.get(u):
                    res.append((u,d))
    else:
        for ms in msg:
            if ms.is_text() and len(i:=str(ms))<=2:
                u = multichar_ord(i)
                if d:=emojis.get(u):
                    res.append((u,d))
            if ms.type=='face':
                e = qqface.get(int(ms.data['id']))
                u = f"{e:x}"
                d = emojis.get(u)
                if d:
                    res.append((u,d))
    if len(res) == 2:
        state['emojimix'] = res
        return True
    else:
        return False
    
@sv.on_command("testemoji",permission=SUPERUSER)
async def _(matcher:Matcher,event: MessageEvent):
    msg = []
    msg.append(str(event.message))
    msg.append(event.raw_message)
    msg.append(str([ord(i)for i in event.get_plaintext()]))
    msg.append(str([ord(i)for i in event.raw_message]))
    await matcher.send("\n".join(msg))
    
@sv.on_message(rule=emojimatch)
async def _ (matcher:Matcher, state: T_State):
    res = state['emojimix']
    r1,d1 = res[0]
    r2,d2 = res[1]
    r1 = r1.replace("fe0f","ufe0f")
    r2 = r2.replace("fe0f","ufe0f")
    # left
    url = bed % (d1,r1,r1,r2)
    resp = await aiohttpx.head(url)
    if resp.ok:
        await matcher.finish(MessageSegment.image(url))
    # right
    url = bed % (d2,r2,r2,r1)
    resp = await aiohttpx.head(url)
    if resp.ok:
        await matcher.finish(MessageSegment.image(url))
    