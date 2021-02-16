import urllib
from hoshino import Service,Bot,MessageSegment
from hoshino.rule import ArgumentParser
from hoshino.typing import T_State
sv=Service('5000choyen',enable_on_default=False)
parser=ArgumentParser()
parser.add_argument('upper')
parser.add_argument('lower')
choyen=sv.on_shell_command('5k',aliases={'5000','5000choyen','5kchoyen'},parser=parser,only_group=False)
@choyen.handle()
async def _(bot:Bot,state:T_State):
    try:
        upper=state['args'].upper
        lower=state['args'].lower
    except:
        pass
    upper=urllib.parse.quote(upper)
    lower=urllib.parse.quote(lower)
    pic=f'https://api.akiraxie.me/5000choyen?upper={upper}&lower={lower}'
    await choyen.finish(MessageSegment.image(pic))
