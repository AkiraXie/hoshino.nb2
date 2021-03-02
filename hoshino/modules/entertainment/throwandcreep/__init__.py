from .util import throw, creep
from hoshino import Service, Bot, Event, T_State, permission
sv = Service('throwandcreep', enable_on_default=False,
             visible=False, manage_perm=permission.SUPERUSER)


@sv.on_keyword({'丢','dio'},state={'action': 'throw'})
@sv.on_keyword(('爬','爪巴'),state={'action': 'creep'})
async def _(bot: Bot, event: Event, state: T_State):
    qq=''
    msg=event.get_message()
    for seg in msg:
        if seg.type=='at':
            qq=int(seg.data['qq'])
            break
    if qq == '' or qq== 'all':
        return
    reply = await throw(qq) if state['action']=='throw' else await creep(qq)
    if not reply==-1:
        await bot.send(event,reply)
    else:
        await bot.send(event,f'{state["action"]}失败，请稍后再试')
    
