'''
Author: AkiraXie
Date: 2021-01-30 01:14:50
LastEditors: AkiraXie
LastEditTime: 2021-01-30 02:02:49
Description: 
Github: http://github.com/AkiraXie/
'''
from hoshino import Bot, Event
from hoshino.util import sucmd
from .util import download_chara_icon
dlicon = sucmd('下载头像')
dlcard = sucmd('下载卡面')
STARS = [1, 3, 6]


@dlicon.handle()
async def _(bot: Bot, event: Event):
    msgs = event.get_plaintext().strip().split()
    ids = list(filter(lambda x: x.isdigit(), msgs))
    replys = ["本次下载头像情况:"]
    for c in ids:
        for star in STARS:
            code, s = await download_chara_icon(c, star)
            status = '成功' if code == 0 else '失败'
            replys.append(f'id:{c},star:{s},下载头像{status}')
    await dlicon.finish('\n'.join(replys))
