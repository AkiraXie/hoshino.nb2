import shutil
from hoshino import Service, Matcher, MessageSegment, T_State
from hoshino.permission import SUPERUSER
import os
import random
from pathlib import Path



# compatiable with lagrange
import pypinyin
def pinyin(s):
    return "".join([i[0] for i in pypinyin.pinyin(s,style=pypinyin.Style.TONE3,errors="ignore")])

os.makedirs(os.path.dirname(__file__)+'/pinyin_images',exist_ok=True)

for f in Path(os.path.dirname(__file__)+'/images').iterdir():
    if f.is_file() :
        new_name = pinyin(f.stem)+'.jpg'
        new_file = os.path.dirname(__file__)+'/pinyin_images/'+new_name
        shutil.copy2(f, new_file)


sv = Service('foods', enable_on_default=False,manage_perm=SUPERUSER)
foods = [i for i in Path(os.path.dirname(__file__)+'/images').iterdir()]
@sv.on_regex(r'(.{1,6})吃(什么|啥)')
async def _(m:Matcher,s:T_State):
    r=random.SystemRandom()
    res = r.choice(foods)
    name = s["_matched_groups"][0]
    new_name = pinyin(res.stem)+'.jpg'
    img = MessageSegment.image(Path(os.path.dirname(__file__)+'/pinyin_images/'+new_name))
    await m.send(f'{name}吃{res.stem}吧! \n'+img,call_header=True)