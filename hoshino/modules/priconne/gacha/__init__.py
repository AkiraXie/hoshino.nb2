"""
Author: AkiraXie
Date: 2021-01-30 21:55:30
LastEditors: AkiraXie
LastEditTime: 2021-03-31 21:18:58
Description: 
Github: http://github.com/AkiraXie/
"""
from nonebot.params import Depends
from hoshino.typing import T_State
from hoshino.util import (
    DailyNumberLimiter,
    img_to_bytes,
    concat_pic,
    normalize_str,
    sucmd,
    parse_qq,
)
from hoshino import MessageSegment, Message, Service, permission, Bot, Event, Matcher
from hoshino.event import GroupMessageEvent, PrivateMessageEvent
from nonebot.exception import FinishedException
from hoshino.modules.priconne.chara import Chara

sv = Service("gacha")
from .gacha import Gacha
from .data import set_collection, set_pool, select_collection, get_pool

jewel_limit = DailyNumberLimiter(7500)
tenjo_limit = DailyNumberLimiter(1)


JEWEL_EXCEED_NOTICE = f"您今天已经抽过{jewel_limit.max}钻了，欢迎明早5点后再来！"
TENJO_EXCEED_NOTICE = f"您今天已经抽过{tenjo_limit.max}张天井券了，欢迎明早5点后再来！"
gacha_10_aliases = {
    "抽十连",
    "十连",
    "十连！",
    "十连抽",
    "来个十连",
    "来发十连",
    "来次十连",
    "抽个十连",
    "抽发十连",
    "抽次十连",
    "十连扭蛋",
    "扭蛋十连",
    "10连",
    "10连！",
    "10连抽",
    "来个10连",
    "来发10连",
    "来次10连",
    "抽个10连",
    "抽发10连",
    "抽次10连",
    "10连扭蛋",
    "扭蛋10连",
    "十連",
    "十連！",
    "十連抽",
    "來個十連",
    "來發十連",
    "來次十連",
    "抽個十連",
    "抽發十連",
    "抽次十連",
    "十連轉蛋",
    "轉蛋十連",
    "10連",
    "10連！",
    "10連抽",
    "來個10連",
    "來發10連",
    "來次10連",
    "抽個10連",
    "抽發10連",
    "抽次10連",
    "10連轉蛋",
    "轉蛋10連",
}
gacha_1_aliases = {
    "单抽",
    "单抽！",
    "来发单抽",
    "来个单抽",
    "来次单抽",
    "扭蛋单抽",
    "单抽扭蛋",
    "單抽",
    "單抽！",
    "來發單抽",
    "來個單抽",
    "來次單抽",
    "轉蛋單抽",
    "單抽轉蛋",
}
gacha_300_aliases = {"抽一井", "来一井", "来发井", "抽发井", "天井扭蛋", "扭蛋天井", "天井轉蛋", "轉蛋天井", "抽井"}


gacha1 = sv.on_command("gacha1", aliases=gacha_1_aliases, only_group=False)
gacha10 = sv.on_command("gacha10", aliases=gacha_10_aliases, only_group=False)
gacha300 = sv.on_command("gacha300", aliases=gacha_300_aliases, only_group=False)
showcol = sv.on_command("仓库", aliases={"查看仓库", "我的仓库", "看看仓库"}, only_group=False)


async def check_jewel_num(matcher: Matcher, event: Event):
    uid = event.get_user_id()
    if not jewel_limit.check(uid):
        await matcher.finish(JEWEL_EXCEED_NOTICE, call_header=True)


async def check_tenjo_num(matcher: Matcher, event: Event):
    uid = event.get_user_id()
    if not tenjo_limit.check(uid):
        await matcher.finish(TENJO_EXCEED_NOTICE, call_header=True)


def get_gacha():
    async def inner(event: Event) -> Gacha:
        if isinstance(event, GroupMessageEvent):
            gid = event.group_id
        elif isinstance(event, PrivateMessageEvent):
            gid = event.user_id * 100
        pool = get_pool(gid)
        return Gacha(pool)

    return Depends(inner)


async def lookup_handler(matcher: Matcher, gacha: Gacha = get_gacha()):
    up_chara = gacha.up
    up_chara = map(
        lambda x: str(Chara.fromid(x).icon.CQcode) + Chara.fromid(x).name, up_chara
    )
    up_chara = "\n".join(up_chara)
    msg = f"本期{gacha.name}卡池主打的角色：\n{up_chara}\nUP角色合计={(gacha.up_prob/10):.1f}% 3★出率={(gacha.s3_prob)/10:.1f}%"
    await matcher.finish(Message(msg))


lookup = sv.on_command(
    "看看卡池",
    aliases={"查看卡池", "康康卡池", "卡池資訊", "看看up", "kkup", "看看UP", "卡池资讯"},
    only_group=False,
    handlers=[lookup_handler],
)


async def lookpool_handler(bot: Bot, event: Event, state: T_State):
    match = state["match"]
    name = match.group(1)
    if name in ("b", "b服", "bl", "bilibili", "国", "国服", "cn"):
        pool = "BL"
    elif name in ("台", "台服", "tw", "sonet"):
        pool = "TW"
    elif name in ("日", "日服", "jp", "cy", "cygames"):
        pool = "JP"
    elif name in ("混", "混合", "mix"):
        pool = "MIX"
    elif name:
        await bot.send(event, "查看卡池失败,未识别{}".format(name))
        raise FinishedException
    gacha = Gacha(pool)
    up_chara = gacha.up
    up_chara = map(lambda x: str(Chara.fromname(x).icon.CQcode) + x, up_chara)
    up_chara = "\n".join(up_chara)
    msg = f"本期{pool}卡池主打的角色：\n{up_chara}\nUP角色合计={(gacha.up_prob/10):.1f}% 3★出率={(gacha.s3_prob)/10:.1f}%"
    await bot.send(event, Message(msg))
    raise FinishedException


lookpool = sv.on_regex(
    r"^(看看|康康|查看)(.{1,10})卡池$", only_group=False, handlers=[lookpool_handler]
)


async def parse_pool(bot: Bot, event: Event, state: T_State):
    if isinstance(event, GroupMessageEvent):
        state["gid"] = event.group_id
    elif isinstance(event, PrivateMessageEvent):
        state["gid"] = event.user_id * 100
    name = normalize_str(event.get_plaintext().strip())
    if name in ("b", "b服", "bl", "bilibili", "国", "国服", "cn"):
        state["pool"] = "BL"
    elif name in ("台", "台服", "tw", "sonet"):
        state["pool"] = "TW"
    elif name in ("日", "日服", "jp", "cy", "cygames"):
        state["pool"] = "JP"
    elif name in ("混", "混合", "mix"):
        state["pool"] = "MIX"
    elif name:
        await bot.send(event, "切换卡池失败,未识别{}".format(name))
        raise FinishedException


switchpool = sv.on_command(
    "切换卡池",
    aliases={"选择卡池", "切換卡池", "選擇卡池", "设置卡池"},
    only_group=False,
    handlers=[parse_pool],
    permission=permission.PADMIN,
)


@switchpool.got(
    "pool", prompt="请输入要切换的卡池:\n> mix\n> jp\n> tw\n> bl", args_parser=parse_pool
)
async def _(matcher: Matcher, state: T_State):
    if state["pool"]:
        set_pool(state["gid"], state["pool"])
        await switchpool.send("卡池已切换为{}池".format(state["pool"]))
        await lookup_handler(matcher, Gacha(state["pool"]))


@gacha1.handle(parameterless=[Depends(check_jewel_num)])
async def _(event: Event, gacha: Gacha = get_gacha()):
    uid = event.get_user_id()
    jewel_limit.increase(uid, 150)
    chara, _ = gacha.gacha_one(gacha.up_prob, gacha.s3_prob, gacha.s2_prob)
    if chara.star == 3:
        set_collection(uid, chara.id)
    res = f'{chara.icon.CQcode}\n{chara.name} {"★"*chara.star}'
    await gacha1.finish(Message(f"素敵な仲間が増えますよ！\n{res}"), call_header=True)


@gacha10.handle(parameterless=[Depends(check_jewel_num)])
async def _(event: Event, gacha: Gacha = get_gacha()):
    uid = event.get_user_id()
    jewel_limit.increase(uid, 1500)
    result, hiishi = gacha.gacha_ten()
    for c in result:
        if 3 == c.star:
            set_collection(uid, c.id)
    res1 = Chara.gen_team_pic(result[:5], star_slot_verbose=False)
    res2 = Chara.gen_team_pic(result[5:], star_slot_verbose=False)
    res = concat_pic([res1, res2])
    res = img_to_bytes(res)
    res = MessageSegment.image(res)
    result = [f'{c.name}{"★"*c.star}' for c in result]
    res1 = " ".join(result[0:5])
    res2 = " ".join(result[5:])
    res = f"{res}\n{res1}\n{res2}"
    if hiishi >= 130:
        await gacha10.send("恭喜海豹！おめでとうございます！")
    await gacha10.finish(Message(f"素敵な仲間が増えますよ！\n{res}"), call_header=True)


@gacha300.handle([Depends(check_tenjo_num)])
async def _(event: Event, gacha: Gacha = get_gacha()):
    uid = int(event.get_user_id())
    tenjo_limit.increase(uid)
    result, up = gacha.gacha_tenjou()
    s3 = len(result["s3"])
    s2 = len(result["s2"])
    s1 = len(result["s1"])
    res = result["s3"]
    for c in res:
        set_collection(uid, c.id)
    lenth = len(res)
    if lenth == 0:
        res = "竟...竟然没有3★？！"
    else:
        step = 4
        pics = []
        for i in range(0, lenth, step):
            j = min(lenth, i + step)
            pics.append(Chara.gen_team_pic(res[i:j], star_slot_verbose=False))
        res = concat_pic(pics)
        res = img_to_bytes(res)
        res = MessageSegment.image(res)
    msg = [
        f"素敵な仲間が増えますよ！ {res}",
        f"★★★×{s3} ★★×{s2} ★×{s1}",
        f"获得{up}个up角色与女神秘石×{50*(s3) + 10*s2 + s1}！\n第{result['first_up_pos']}抽首次获得up角色"
        if up
        else f"获得女神秘石{50*(up+s3) + 10*s2 + s1}个！",
    ]
    if up == 0 and s3 == 0:
        msg.append("太惨了，咱们还是退款删游吧...")
    elif up == 0 and s3 > 7:
        msg.append("up呢？我的up呢？")
    elif up == 0 and s3 <= 3:
        msg.append("这位酋长，大月卡考虑一下？")
    elif up == 0:
        msg.append("据说天井的概率只有12.16%")
    elif up <= 2:
        if result["first_up_pos"] < 50:
            msg.append("你的喜悦我收到了，滚去喂鲨鱼吧！")
        elif result["first_up_pos"] < 100:
            msg.append("已经可以了，您已经很欧了")
        elif result["first_up_pos"] > 290:
            msg.append("标 准 结 局")
        elif result["first_up_pos"] > 250:
            msg.append("补井还是不补井，这是一个问题...")
        else:
            msg.append("期望之内，亚洲水平")
    elif up == 3:
        msg.append("抽井母五一气呵成！您就是欧洲人？")
    elif up >= 4:
        msg.append("记忆碎片一大堆！您是托吧？")
    await gacha300.finish(Message("\n".join(msg)), call_header=True)


@showcol.handle()
async def _(event: Event):
    uid = int(event.get_user_id())
    col = select_collection(uid)
    length = len(col)
    if length <= 0:
        await showcol.finish("您的仓库为空,请多多抽卡哦~", call_header=True)
    result = list(map(lambda x: Chara.fromid(x), col))
    step = 6
    pics = []
    for i in range(0, length, step):
        j = min(length, i + step)
        pics.append(Chara.gen_team_pic(result[i:j], star_slot_verbose=False))
    res = concat_pic(pics)
    res = img_to_bytes(res)
    res = MessageSegment.image(res)
    msg = [f"仅展示三星角色~", f"{res}", f"您共有{length}个三星角色~"]
    await showcol.finish(Message("\n".join(msg)), call_header=True)


kakin = sucmd("氪金", aliases={"充值"}, handlers=[parse_qq])


@kakin.got("ids", prompt="请输入要充值的id,并用空格隔开~\n在群聊中，还支持直接at哦~", args_parser=parse_qq)
async def _(state: T_State):
    if not state["ids"]:
        await kakin.finish()
    count = 0
    for id in state["ids"]:
        id = str(id)
        jewel_limit.reset(id)
        tenjo_limit.reset(id)
        count += 1
    await kakin.finish(f"已为{count}位用户充值完毕！谢谢惠顾～")
