"""
Author: AkiraXie
Date: 2021-01-30 15:00:40
LastEditors: AkiraXie
LastEditTime: 2021-02-02 23:34:36
Description: 
Github: http://github.com/AkiraXie/
"""
import random
from typing import List, Tuple
from . import Chara, sv


class Gacha(object):
    def __init__(self, pool_name: str = "MIX"):
        config = sv.config
        pool = config[pool_name]
        self.name = pool_name
        self.up_prob = pool["up_prob"]
        self.s3_prob = pool["s3_prob"]
        self.s2_prob = pool["s2_prob"]
        self.up = pool["up"]
        self.star3 = pool["star3"]
        self.star2 = pool["star2"]
        self.star1 = pool["star1"]

    def gacha_one(self, up_prob: int, s3_prob: int, s2_prob: int) -> Tuple[Chara, int]:
        """
        sx_prob: x星概率，要求和为1000
        up_prob: UP角色概率（从3星划出）
        up_chara: UP角色名列表

        return: (单抽结果:Chara, 秘石数:int)
        ---------------------------
        |up|      |  20  |   78   |
        |   ***   |  **  |    *   |
        ---------------------------
        """
        rn = random.SystemRandom()
        pick = rn.randint(1, 1000)
        if pick <= up_prob:
            return Chara.fromid(rn.choice(self.up), 3), 100
        elif pick <= s3_prob:
            return Chara.fromid(rn.choice(self.star3), 3), 50
        elif pick <= s2_prob + s3_prob:
            return Chara.fromid(rn.choice(self.star2), 2), 10
        else:
            return Chara.fromid(rn.choice(self.star1), 1), 1

    def gacha_ten(self) -> Tuple[List[Chara], int]:
        result = []
        hiishi = 0
        up = self.up_prob
        s3 = self.s3_prob
        s2 = self.s2_prob
        for _ in range(9):  # 前9连
            c, y = self.gacha_one(up, s3, s2)
            result.append(c)
            hiishi += y if y != 100 else 50
        c, y = self.gacha_one(up, s3, 1000 - s3)  # 保底第10抽
        result.append(c)
        hiishi += y if y != 100 else 50

        return result, hiishi

    def gacha_tenjou(self) -> Tuple:
        result = {"s3": [], "s2": [], "s1": []}
        first_up_pos = 999
        upnum = 0
        up = self.up_prob
        s3 = self.s3_prob
        s2 = self.s2_prob
        num: int
        if self.name != "BL":
            num = 20
        else:
            num = 30
        for i in range(num):
            for j in range(1, 10):  # 前9连
                c, y = self.gacha_one(up, s3, s2)
                if 100 == y:
                    result["s3"].append(c)
                    first_up_pos = min(i * 10 + j, first_up_pos)
                    upnum += 1
                elif 50 == y:
                    result["s3"].append(c)
                elif 10 == y:
                    result["s2"].append(c)
                elif 1 == y:
                    result["s1"].append(c)
            c, y = self.gacha_one(up, s3, 1000 - s3)  # 保底第10抽
            if 100 == y:
                result["s3"].append(c)
                first_up_pos = min((i + 1) * 10, first_up_pos)
                upnum += 1
            elif 50 == y:
                result["s3"].append(c)
            elif 10 == y:
                result["s2"].append(c)
            elif 1 == y:
                result["s1"].append(c)
        result["first_up_pos"] = first_up_pos
        return result, upnum
