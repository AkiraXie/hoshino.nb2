'''
Author: AkiraXie
Date: 2022-03-08 01:26:38
LastEditors: AkiraXie
LastEditTime: 2022-03-08 03:09:36
Description: 
Github: http://github.com/AkiraXie/
'''

## Thanks to github.com/FloatTech/ZeroBot-Plugin/plugin/emojimix

from hoshino import Service, T_State,aiohttpx,Matcher,MessageSegment,SUPERUSER
from hoshino.event import MessageEvent
from .data import emojis, qqface

sv = Service("emojimix",visible=False,enable_on_default=False)

bed = "https://www.gstatic.com/android/keyboard/emojikitchen/%d/u%x/u%x_u%x.png"

async def emojimatch(event: MessageEvent, state: T_State):
    msg = event.get_message()
    res = []
    if len(msg)>2:
        return False
    if len(msg)==1:
        text = event.get_plaintext()
        if len(text)!=2:
            return False
        for i in text:
            u = ord(i)
            if d:=emojis.get(u):
                res.append((u,d))
    else:
        for ms in msg:
            if ms.is_text() and len(i:=str(ms))==1:
                u = ord(i)
                if d:=emojis.get(u):
                    res.append((u,d))
            if ms.type=='face':
                e = qqface.get(int(ms.data['id']))
                d = emojis.get(e)
                if d:
                    res.append((e,d))
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
    