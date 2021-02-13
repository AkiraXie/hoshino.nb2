from enum import IntEnum, auto
from functools import lru_cache
from typing import Union


class PcrdCampaignCategory(IntEnum):
    none = 0
    halfStaminaNormal = 11
    halfStaminaHard = auto()
    halfStaminaBoth = auto()
    halfStaminaShrine = auto()
    halfStaminaTemple = auto()
    halfStaminaVeryHard = auto()

    dropRareNormal = 21
    dropRareHard = auto()
    dropRareBoth = auto()
    dropRareVeryHard = auto()

    dropAmountNormal = 31
    dropAmountHard = auto()
    dropAmountBoth = auto()
    dropAmountExploration = auto()
    dropAmountDungeon = auto()
    dropAmountCoop = auto()
    dropAmountShrine = auto()
    dropAmountTemple = auto()
    dropAmountVeryHard = auto()

    manaNormal = 41
    manaHard = auto()
    manaBoth = auto()
    manaExploration = auto()
    manaDungeon = auto()
    manaCoop = auto()
    manaTemple = 48
    manaVeryHard = auto()

    coinDungeon = 51

    cooltimeArena = 61
    cooltimeGrandArena = auto()

    masterCoin = 90
    masterCoinNormal = auto()
    masterCoinHard = auto()
    masterCoinVeryHard = auto()
    masterCoinShrine = auto()
    masterCoinTemple = auto()
    masterCoinEventNormal = auto()
    masterCoinEventHard = auto()
    masterCoinRevivalEventNormal = auto()
    masterCoinRevivalEventHard = auto()

    halfStaminaEventNormal = 111
    halfStaminaEventHard = auto()
    halfStaminaEventBoth = auto()

    dropRareEventNormal = 121
    dropRareEventHard = auto()
    dropRareEventBoth = auto()

    dropAmountEventNormal = 131
    dropAmountEventHard = auto()
    dropAmountEventBoth = auto()

    manaEventNormal = 141
    manaEventHard = auto()
    manaEventBoth = auto()

    expEventNormal = 151
    expEventHard = auto()
    expEventBoth = auto()

    halfStaminaRevivalEventNormal = 211
    halfStaminaRevivalEventHard = auto()

    dropRareRevivalEventNormal = 221
    dropRareRevivalEventHard = auto()

    dropAmountRevivalEventNormal = 231
    dropAmountRevivalEventHard = auto()

    manaRevivalEventNormal = 241
    manaRevivalEventHard = auto()

    expRevivalEventNormal = 251
    expRevivalEventHard = auto()

    halfStaminaSideStoryNormal = 311
    halfStaminaSideStoryHard = auto()

    dropRareSideStoryNormal = 321
    dropRareSideStoryHard = auto()

    dropAmountSideStoryNormal = 331
    dropAmountSideStoryHard = auto()

    manaSideStoryNormal = 341
    manaSideStoryHard = auto()

    expSideStoryNormal = 351
    expSideStoryHard = auto()


short_name = {
    'manaDungeon': '地城',
    'masterCoinNormal': '大师',
    'dropAmountNormal': 'N 图',
    'dropAmountHard': 'H 图',
    'dropAmountEventNormal': '活动N图',
    'dropAmountEventHard': '活动H图',
    'dropAmountShrine': '圣迹',
    'dropAmountTemple': '神殿',
    'manaExploration': '探索',
    'dropAmountVeryHard': 'VH图',
}


@lru_cache(maxsize=128)
def parse_campaign(cata: int) -> Union[int, None]:
    try:
        c = PcrdCampaignCategory(cata)
    except ValueError:
        return None
    name = short_name.get(c.name)
    return name