'''
Author: AkiraXie
Date: 2021-01-30 21:55:30
LastEditors: AkiraXie
LastEditTime: 2021-01-31 04:13:16
Description: 
Github: http://github.com/AkiraXie/
'''

from hoshino.typing import T_State
from hoshino.util import DailyNumberLimiter, pic2b64, concat_pic, normalize_str, sucmd
from hoshino import MessageSegment, Message, Service, permission, Bot, Event
from hoshino.event import GroupMessageEvent, PrivateMessageEvent
from hoshino.matcher import Matcher, matcher_send

from hoshino.modules.priconne.chara import Chara
from .util import Gacha
from .data import set_collection, set_pool, select_collection, get_pool

sv = Service('gacha')
jewel_limit = DailyNumberLimiter(7500)
tenjo_limit = DailyNumberLimiter(1)


JEWEL_EXCEED_NOTICE = f'您今天已经抽过{jewel_limit.max}钻了，欢迎明早5点后再来！'
TENJO_EXCEED_NOTICE = f'您今天已经抽过{tenjo_limit.max}张天井券了，欢迎明早5点后再来！'
POOL = ('MIX', 'JP', 'TW', 'BL')
gacha_10_aliases = {'抽十连', '十连', '十连！', '十连抽', '来个十连', '来发十连', '来次十连', '抽个十连', '抽发十连', '抽次十连', '十连扭蛋', '扭蛋十连',
                    '10连', '10连！', '10连抽', '来个10连', '来发10连', '来次10连', '抽个10连', '抽发10连', '抽次10连', '10连扭蛋', '扭蛋10连',
                    '十連', '十連！', '十連抽', '來個十連', '來發十連', '來次十連', '抽個十連', '抽發十連', '抽次十連', '十連轉蛋', '轉蛋十連',
                    '10連', '10連！', '10連抽', '來個10連', '來發10連', '來次10連', '抽個10連', '抽發10連', '抽次10連', '10連轉蛋', '轉蛋10連'}
gacha_1_aliases = {'单抽', '单抽！', '来发单抽', '来个单抽', '来次单抽', '扭蛋单抽', '单抽扭蛋',
                   '單抽', '單抽！', '來發單抽', '來個單抽', '來次單抽', '轉蛋單抽', '單抽轉蛋'}
gacha_300_aliases = {'抽一井', '来一井', '来发井', '抽发井', '天井扭蛋',
                     '扭蛋天井', '天井轉蛋', '轉蛋天井', '抽井'}

lookup = sv.on_command("看看卡池", aliases={
    '查看卡池',  '康康卡池', '卡池資訊', '看看up', 'kkup', '看看UP', '卡池资讯'}, only_group=False)
switchpool = sv.on_command("切换卡池", aliases={
    '选择卡池', '切換卡池', '選擇卡池'}, only_group=False)
gacha1 = sv.on_command('gacha1', aliases=gacha_1_aliases, only_group=False)

gacha10 = sv.on_command('gacha10', aliases=gacha_10_aliases, only_group=False)
gacha300 = sv.on_command(
    'gacha300', aliases=gacha_300_aliases, only_group=False)
kakin = sucmd('氪金', aliases={'充值'})
showcol = sv.on_command('仓库',  aliases={
    '查看仓库', '我的仓库', '看看仓库'}, only_group=False)

async def check_jewel_num(mathcer: Matcher, event: Event):
    uid = event.get_user_id()
    if not jewel_limit.check(int(uid)):
        await matcher_send(mathcer, event, JEWEL_EXCEED_NOTICE, True, True)


async def check_tenjo_num(mathcer: Matcher, event: Event):
    uid = event.get_user_id()
    if not tenjo_limit.check(int(uid)):
        await matcher_send(mathcer, event, TENJO_EXCEED_NOTICE, True, True)


@lookup.handle()
async def _(bot: Bot, event: Event):
    if isinstance(event, GroupMessageEvent):
        gid = event.group_id
    elif isinstance(event, PrivateMessageEvent):
        gid = event.user_id*100

    pool = get_pool(gid)
    gacha = Gacha(pool)
    up_chara = gacha.up
    up_chara = map(lambda x: str(
        Chara.fromname(x).icon.CQcode) + x, up_chara)
    await lookup.finish(Message('\n'.join(up_chara)))


@switchpool.handle()
async def _(bot: Bot, event: Event, state: T_State):
    if isinstance(event, GroupMessageEvent):
        state['gid'] = event.group_id
    elif isinstance(event, PrivateMessageEvent):
        state['gid'] = event.user_id*100
    name = normalize_str(event.get_plaintext().strip())
    if name in ('b', 'b服', 'bl', 'bilibili', '国', '国服', 'cn'):
        state['pool'] = 'BL'
    elif name in ('台', '台服', 'tw', 'sonet'):
        state['pool'] = 'TW'
    elif name in ('日', '日服', 'jp', 'cy', 'cygames'):
        state['pool'] = 'JP'
    elif name in ('混', '混合', 'mix'):
        state['pool'] = 'MIX'
    elif name:
        await switchpool.finish('切换卡池失败,未识别{}'.format(name))


@switchpool.got('pool', prompt='请输入要切换的卡池:\n> jp\n> tw\n> bl')
async def _(bot: Bot, event: Event, state: T_State):
    name = normalize_str(event.get_plaintext().strip())
    if name in ('b', 'b服', 'bl', 'bilibili', '国', '国服', 'cn'):
        state['pool'] = 'BL'
    elif name in ('台', '台服', 'tw', 'sonet'):
        state['pool'] = 'TW'
    elif name in ('日', '日服', 'jp', 'cy', 'cygames'):
        state['pool'] = 'JP'
    elif name in ('混', '混合', 'mix'):
        state['pool'] = 'MIX'
    elif name:
        await switchpool.finish('切换卡池失败,未识别{}'.format(name))
    set_pool(state['gid'], state['pool'])
    await switchpool.finish('卡池已切换为{}池'.format(state['pool']))


@gacha1.handle()
async def _(bot: Bot, event: Event):
    await check_jewel_num(gacha1, event)
    uid = int(event.get_user_id())
    jewel_limit.increase(uid, 150)
    if isinstance(event, GroupMessageEvent):
        gid = event.group_id
    elif isinstance(event, PrivateMessageEvent):
        gid = event.user_id*100
    pool = get_pool(gid)
    gacha = Gacha(pool)
    chara, _ = gacha.gacha_one(
        gacha.up_prob, gacha.s3_prob, gacha.s2_prob)
    if chara.star == 3:
        set_collection(uid, chara.id)
    res = f'{chara.icon.CQcode}\n{chara.name} {"★"*chara.star}'
    await matcher_send(gacha1, event, f'素敵な仲間が増えますよ！\n{res}', True, True)


@gacha10.handle()
async def _(bot: Bot, event: Event):
    SUPER_LUCKY_LINE = 130
    await check_jewel_num(gacha10, event)
    uid = int(event.get_user_id())
    jewel_limit.increase(uid, 1500)
    if isinstance(event, GroupMessageEvent):
        gid = event.group_id
    elif isinstance(event, PrivateMessageEvent):
        gid = event.user_id*100
    pool = get_pool(gid)
    gacha = Gacha(pool)
    result, hiishi = gacha.gacha_ten()
    for c in result:
        if 3 == c.star:
            set_collection(uid, c.id)
    res1 = Chara.gen_team_pic(result[:5], star_slot_verbose=False)
    res2 = Chara.gen_team_pic(result[5:], star_slot_verbose=False)
    res = concat_pic([res1, res2])
    res = pic2b64(res)
    res = MessageSegment.image(res)
    result = [f'{c.name}{"★"*c.star}' for c in result]
    res1 = ' '.join(result[0:5])
    res2 = ' '.join(result[5:])
    res = f'{res}\n{res1}\n{res2}'
    if hiishi >= SUPER_LUCKY_LINE:
        gacha10.send('恭喜海豹！おめでとうございます！')
    await matcher_send(gacha10, event, f'素敵な仲間が増えますよ！\n{res}', True, True)


@gacha300.handle()
async def _(bot: Bot, event: Event):
    await check_tenjo_num(gacha300, event)
    uid = int(event.get_user_id())
    tenjo_limit.increase(uid)
    if isinstance(event, GroupMessageEvent):
        gid = event.group_id
    elif isinstance(event, PrivateMessageEvent):
        gid = event.user_id*100
    pool = get_pool(gid)
    gacha = Gacha(pool)
    result, up = gacha.gacha_tenjou()
    s3 = len(result['s3'])
    s2 = len(result['s2'])
    s1 = len(result['s1'])
    res = result['s3']
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
        res = pic2b64(res)
        res = MessageSegment.image(res)
    msg = [
        f"素敵な仲間が増えますよ！ {res}",
        f"★★★×{s3} ★★×{s2} ★×{s1}",
        f"获得{up}个up角色与女神秘石×{50*(s3) + 10*s2 + s1}！\n第{result['first_up_pos']}抽首次获得up角色" if up else f"获得女神秘石{50*(up+s3) + 10*s2 + s1}个！"
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
        if result['first_up_pos'] < 50:
            msg.append("你的喜悦我收到了，滚去喂鲨鱼吧！")
        elif result['first_up_pos'] < 100:
            msg.append("已经可以了，您已经很欧了")
        elif result['first_up_pos'] > 290:
            msg.append("标 准 结 局")
        elif result['first_up_pos'] > 250:
            msg.append("补井还是不补井，这是一个问题...")
        else:
            msg.append("期望之内，亚洲水平")
    elif up == 3:
        msg.append("抽井母五一气呵成！您就是欧洲人？")
    elif up >= 4:
        msg.append("记忆碎片一大堆！您是托吧？")
    await matcher_send(gacha300, event, '\n'.join(msg), True, True)
@showcol.handle()
async def _(bot: Bot, event: Event):
    uid = int(event.get_user_id())
    col=select_collection(uid)
    length = len(col)
    if length <= 0:
        await matcher_send(showcol, event, '您的仓库为空,请多多抽卡哦~', True, True)
    result = list(map(lambda x: Chara.fromid(x), col))
    step = 6
    pics = []
    for i in range(0, length, step):
        j = min(length, i + step)
        pics.append(Chara.gen_team_pic(
            result[i:j], star_slot_verbose=False))
    res = concat_pic(pics)
    res = pic2b64(res)
    res = MessageSegment.image(res)
    msg = [
        f'仅展示三星角色~',
        f'{res}',
        f'您共有{length}个三星角色~'
    ]
    await matcher_send(showcol, event, '\n'.join(msg), True, True)
    
    
async def parse_qq(bot: Bot, event: Event,state:T_State):
    ids=[]
    if isinstance(event,GroupMessageEvent):
        for m in event.get_message():
            if m.type=='at' and m.data['qq'] != 'all':
                ids.append(int(m.data['qq']))
            elif m.type=='text' and m.data['text'].isdigit():
                ids.append(int(m.data['text']))
    elif isinstance(event,PrivateMessageEvent):
        for m in event.get_plaintext().split():
            if m.isdigit():
                ids.append(int(m.data['text']))
    if ids:
        state['ids']=ids.copy()
@kakin.handle()
async def _(bot: Bot, event: Event,state:T_State):
    await parse_qq(bot,event,state)


@kakin.got('ids',prompt='请输入要充值的id,并用空格隔开~\n在群聊中，还支持直接at哦~',args_parser=parse_qq)
async def _(bot: Bot, event: Event,state:T_State):
    if not state['ids']:
        await kakin.finish()
    count=0
    for id in state['ids']:
        jewel_limit.reset(id)
        tenjo_limit.reset(id)
        count += 1
    await kakin.finish(f"已为{count}位用户充值完毕！谢谢惠顾～")