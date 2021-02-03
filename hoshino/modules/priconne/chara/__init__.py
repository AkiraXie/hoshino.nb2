'''
Author: AkiraXie
Date: 2021-01-30 01:14:50
LastEditors: AkiraXie
LastEditTime: 2021-02-03 21:47:27
Description: 
Github: http://github.com/AkiraXie/
'''
import os
import pygtrie
import zhconv
import importlib
from PIL import Image, ImageFont
import nonebot
from loguru import logger
from hoshino import Bot, Event, R, rhelper
from hoshino.util import sucmd, get_text_size, text2pic, run_sync
from .util import download_card, download_chara_icon, download_config, download_pcrdata
from hoshino.modules.priconne import _pcr_data
dlicon = sucmd('下载头像')
dlcard = sucmd('下载卡面')
dldata = sucmd('更新卡池', aliases={'更新数据'})
STARS = [1, 3, 6]
TFONT = ImageFont.truetype(R.img('priconne/gadget/FZY3K.TTF').path, 16)
UNKNOWN = 1000
try:
    gadget_equip = R.img('priconne/gadget/equip.png').open()
    gadget_star = R.img('priconne/gadget/star.png').open()
    gadget_star_dis = R.img('priconne/gadget/star_disabled.png').open()
    gadget_star_pink = R.img('priconne/gadget/star_pink.png').open()
    unknown_chara_icon = R.img('priconne/unit/icon_unit_100031.png').open()
except Exception as e:
    logger.exception(e)
os.makedirs(R.img(f'priconne/gadget/').path, exist_ok=True)
os.makedirs(R.img(f'priconne/card/').path, exist_ok=True)
os.makedirs(R.img(f'priconne/unit/').path, exist_ok=True)
NAME2ID = pygtrie.CharTrie()


@dlicon.handle()
async def _(bot: Bot, event: Event):
    msgs = event.get_plaintext().strip().split()
    charas = list(map(lambda x: Chara.fromid(int(x))
                      if x.isdigit() else Chara.fromname(x), msgs))
    replys = ["本次下载头像情况:"]
    for c in charas:
        for star in STARS:
            code, s = await run_sync(download_chara_icon)(c.id, star)
            status = '成功' if code == 0 else '失败: '
            replys.append(f'name:{c.name},id:{c.id},star:{s},下载头像{status}')
            if code != 0:
                replys.append(code)
    await dlicon.finish('\n'.join(replys))


@dlcard.handle()
async def _(bot: Bot, event: Event):
    msgs = event.get_plaintext().strip().split()
    charas = list(map(lambda x: Chara.fromid(int(x))
                      if x.isdigit() else Chara.fromname(x), msgs))
    replys = ["本次下载卡面情况:"]
    for c in charas:
        for star in STARS[1:]:
            code, s = await run_sync(download_card)(c.id, star)
            status = '成功' if code == 0 else '失败'
            replys.append(f'name:{c.name},id:{c.id},star:{s},下载卡面{status}')
            if code != 0:
                replys.append(code)
    await dlcard.finish('\n'.join(replys))


@dldata.handle()
async def _(bot: Bot, event: Event):
    code_1 = await download_pcrdata()
    code_2 = await download_config()
    if code_1 == 0 and code_2 == 0:
        try:
            importlib.reload(_pcr_data)
            Chara.gen_name2id()
        except Exception as e:
            logger.exception(e)
            logger.error(f'重载花名册失败！{type(e)}, {e}')
            await dldata.finish(f'重载花名册失败！错误如下：\n{type(e)}, {e}')

        await dldata.finish('更新卡池和数据成功')
    else:
        exc = filter(lambda x: x != 0, (code_1, code_2))
        exc = "\n".join(exc)
        await dldata.finish(f'更新卡池和数据失败，错误如下：\n {exc}')


class Chara:
    UNKNOWN = 1000

    def __init__(self, id_: int, star: int = 3, equip: int = 0):
        self.id = id_
        self.star = star
        self.equip = equip

    @staticmethod
    def fromid(id_, star=3, equip=0):
        '''Create Chara from her id. The same as Chara()'''
        return Chara(id_, star, equip)

    @staticmethod
    def fromname(name, star=3, equip=0):
        '''Create Chara from her name.'''
        id_ = Chara.name2id(name)
        return Chara(id_, star, equip)

    @property
    def name(self):
        return _pcr_data.CHARA_NAME[self.id][0] if self.id in _pcr_data.CHARA_NAME else _pcr_data.CHARA_NAME[Chara.UNKNOWN][0]

    @property
    def icon(self) -> rhelper:
        if self.star == 0 or self.star == 6:
            star = '6'
        elif 3 <= self.star <= 5:
            star = '3'
        else:
            star = "1"
        res = R.img(f'priconne/unit/icon_unit_{self.id}{star}1.png')
        if not res.exist:
            res = R.img(f'priconne/unit/icon_unit_{self.id}31.png')
        if not res.exist:
            res = R.img(f'priconne/unit/icon_unit_{self.id}11.png')
        if not res.exist:
            download_chara_icon(self.id, 6)
            download_chara_icon(self.id, 3)
            download_chara_icon(self.id, 1)
            res = R.img(f'priconne/unit/icon_unit_{self.id}{star}1.png')
        if not res.exist:
            res = R.img(f'priconne/unit/icon_unit_{self.id}31.png')
        if not res.exist:
            res = R.img(f'priconne/unit/icon_unit_{self.id}11.png')
        if not res.exist:  # should never reach here
            res = R.img(f'priconne/unit/icon_unit_{UNKNOWN}31.png')
        return res

    @property
    def card(self) -> str:
        if self.star == 0 or self.star == 6:
            star = '6'
        elif 3 <= self.star <= 5:
            star = '3'
        else:
            star = "1"
        tip = f"{self.name}{star}星卡面：\n"
        res = R.img(f'priconne/card/{self.id}{star}1.png')
        if not res.exist:
            if self.star == 6:
                tip = f"{self.name}没有6星卡面，将展示3星卡面：\n"
            else:
                tip = f"{self.name}3星卡面：\n"
            res = R.img(f'priconne/card/{self.id}31.png')
        if not res.exist:
            tip = f"{self.name}1星卡面：\n"
            res = R.img(f'priconne/card/{self.id}11.png')
        if not res.exist:
            download_card(self.id, 6)
            download_card(self.id, 3)
            download_card(self.id, 1)
            tip = f"{self.name}{star}星卡面：\n"
            res = R.img(f'priconne/card/{self.id}{star}1.png')
        if not res.exist:
            if self.star == 6:
                tip = f"{self.name}没有6星卡面，将展示3星卡面：\n"
            else:
                tip = f"{self.name}3星卡面：\n"
            res = R.img(f'priconne/card/{self.id}31.png')
        if not res.exist:
            tip = f"{self.name}1星卡面：\n"
            res = R.img(f'priconne/card/{self.id}11.png')
        if not res.exist:  # should never reach here
            tip = ""
            res = R.img(f'priconne/unit/icon_unit_{UNKNOWN}31.png')
        return tip+f'{res.CQcode}'

    def gen_icon_img(self, size, star_slot_verbose=True) -> Image:
        try:
            pic = self.icon.open().convert('RGBA').resize((size, size), Image.LANCZOS)
        except FileNotFoundError:
            logger.error(f'File not found: {self.icon.path}')
            pic = unknown_chara_icon.convert(
                'RGBA').resize((size, size), Image.LANCZOS)

        l = size // 6
        star_lap = round(l * 0.15)
        margin_x = (size - 6*l) // 2
        margin_y = round(size * 0.05)
        if self.star:
            for i in range(5 if star_slot_verbose else min(self.star, 5)):
                a = i*(l-star_lap) + margin_x
                b = size - l - margin_y
                s = gadget_star if self.star > i else gadget_star_dis
                s = s.resize((l, l), Image.LANCZOS)
                pic.paste(s, (a, b, a+l, b+l), s)
            if 6 == self.star:
                a = 5*(l-star_lap) + margin_x
                b = size - l - margin_y
                s = gadget_star_pink
                s = s.resize((l, l), Image.LANCZOS)
                pic.paste(s, (a, b, a+l, b+l), s)
        if self.equip:
            l = round(l * 1.5)
            a = margin_x
            b = margin_x
            s = gadget_equip.resize((l, l), Image.LANCZOS)
            pic.paste(s, (a, b, a+l, b+l), s)
        return pic

    @staticmethod
    def parse_team(namestr: str) -> tuple:
        namestr = Chara.normname(namestr.strip())
        team = []
        unknown = []
        while namestr:
            item = NAME2ID.longest_prefix(namestr)
            if not item:
                unknown.append(namestr[0])
                namestr = namestr[1:].lstrip()
            else:
                team.append(item.value)
                namestr = namestr[len(item.key):].lstrip()
        return team, ''.join(unknown)

    @staticmethod
    def gen_team_pic(team, size=64, star_slot_verbose=True, text=None):
        num = len(team)
        if isinstance(text, str):
            tsize = get_text_size(text, TFONT, padding=(5, 5, 12, 12))
            des = Image.new(
                'RGBA', (num*size+tsize[0], size), (255, 255, 255, 255))
            timg = text2pic(text, TFONT, padding=(5, 5, 12, 12))
            img = Image.new('RGBA', (20, 45), (255, 255, 255, 255))
            like = Image.open(R.img('priconne/gadget/like.png').path)
            dislike = Image.open(R.img('priconne/gadget/dislike.png').path)
            dislike.thumbnail((20, 20))
            like.thumbnail((20, 20))
            img.paste(like, (0, 0), like)
            img.paste(dislike, (0, 25), dislike)
            timg.paste(img, (5, 11), img)
            des.paste(timg, (num * size, 0), timg)
        else:
            des = Image.new('RGBA', (num*size, size), (255, 255, 255, 255))
        for i, chara in enumerate(team):
            src = chara.gen_icon_img(size, star_slot_verbose)
            des.paste(src, (i * size, 0), src)
        return des

    @staticmethod
    def name2id(name):
        name = Chara.normname(name)
        if not NAME2ID:
            Chara.gen_name2id()
        return NAME2ID[name] if name in NAME2ID else UNKNOWN

    @staticmethod
    def gen_name2id():
        NAME2ID.clear()
        for k, v in _pcr_data.CHARA_NAME.items():
            for s in v:
                if s not in NAME2ID:
                    NAME2ID[Chara.normname(s)] = k
                else:
                    logger.warning(
                        f'Chara.gen_name2id: 出现重名{s}于id{k}与id{NAME2ID[s]}')

    @staticmethod
    def normname(name: str) -> str:
        name = name.lower().replace('（', '(').replace('）', ')')
        name = zhconv.convert(name, 'zh-hans')
        return name


Chara.gen_name2id()
nonebot.export()['Chara'] = Chara
