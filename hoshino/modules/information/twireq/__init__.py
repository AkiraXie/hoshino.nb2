import asyncio
import random
from pathlib import Path
from shutil import copy

from hoshino import Bot, Event, Message, MessageSegment, Service, fav_dir, img_dir
from hoshino.schedule import scheduled_job
from nonebot.permission import SUPERUSER

from .util import TwitterDB as db
from .util import get_new_tweetid, get_tweet, get_tweets, lookup_user

sv = Service("twireq", enable_on_default=False)

addtwi = sv.on_command("添加推特", aliases={"订阅推特", "tjtt"})


@addtwi.handle()
async def _(bot: Bot, event: Event):
    uname = event.get_plaintext()
    uname = uname.replace("https://", "").replace("twitter.com/", "").replace("@", "")
    try:
        uid, name, uname = await lookup_user(uname)
    except:
        sv.logger.exception(f"获取{uname} 推特失败")
        await addtwi.finish(f"获取{uname} 推特失败")
    try:
        tid = await get_new_tweetid(uid)
    except:
        sv.logger.exception(f"获取{uname} 推特失败")
        await addtwi.finish(f"获取{uname} 推特失败")
    db.replace(uname=uname, uid=uid, gid=event.group_id, tid=tid, name=name).execute()
    await addtwi.finish(f"{name}(@{uname}) 推特添加成功")


findtwi = sv.on_command("本群推特列表", aliases={"推特列表", "推特订阅列表"})


@findtwi
async def _(bot: Bot, event: Event):
    rows = db.select().where(db.gid == event.group_id)
    if not rows:
        await findtwi.finish("本群暂无推特订阅")
    else:
        rows = list(rows)
        num = len(rows)
        msg = []
        msg.append(f"本群订阅了{num}个推特:")
        if num >= 60:
            rowss = [rows[::3], rows[1::3], rows[2::3]]
            for rs in rowss:
                msg.extend("{}@{}".format(r.name, r.uname) for r in rs)
                await findtwi.send("\n".join(msg))
                await asyncio.sleep(0.3)
                msg = []
        else:
            msg.extend("{}@{}".format(r.name, r.uname) for r in rows)
            await findtwi.send("\n".join(msg))


seetwi = sv.on_command("看推", aliases={"查看推特", "查推"})


@seetwi
async def _(bot: Bot, event: Event):
    name = event.get_plaintext()
    row = db.get_or_none(db.gid == event.group_id, db.uname == name) or db.get_or_none(
        db.gid == event.group_id, db.name == name
    )
    if not row:
        await seetwi.finish("{}查看推特失败".format(name))
    else:
        uid = row.uid
        tws = await get_tweets(uid)
        tw = tws[0]
        await seetwi.finish(tw.get_msg())


def sort_key(x: Path):
    return x.stat().st_ctime


randimg = sv.on_command(
    "随机推特",
    aliases={"randomtwi", "rtwi", "sjtt"},
    only_group=False,
    permission=SUPERUSER,
)


def gen_imgs(lmt: int = 0, fav: bool = False):
    rm = random.SystemRandom()
    img_d = Path(img_dir) if not fav else Path(fav_dir)
    imgs = [i for i in img_d.iterdir()]
    imgs = list(filter(lambda x: x.name.startswith("tweet@"), imgs))
    imgs.sort(key=sort_key)
    if fav:
        return imgs[::-1]
    lens = len(imgs)
    weights = [x + 2 for x in range(lens)]
    lmt = min(lmt, lens) if lmt else lens
    imgs = rm.choices(imgs, weights, k=lmt)
    return imgs


@randimg
async def _(bot: Bot, event: Event):
    imgs = gen_imgs(5)
    for img in imgs:
        msg = [f"RandomTweet {img.stem}"]
        msg.append(str(MessageSegment.image(img)))
        await randimg.send(Message("\n".join(msg)))
        await asyncio.sleep(0.4)


rand30img = sv.on_command(
    "r50", aliases={"sj50", "t50", "随机五十", "看看推", "kkt"}, permission=SUPERUSER
)


@rand30img
async def _(bot: Bot, event: Event):
    def get_node(m):
        c = MessageSegment("node", {"uin": bot.self_id, "name": "女菩萨bot", "content": m})
        return c

    imgs = gen_imgs(50)
    msg = []
    for img in imgs:
        m = f"{img.name}" + MessageSegment.image(img)
        msg.append(get_node(m))
    await bot.call_api("send_group_forward_msg", group_id=event.group_id, messages=msg)


deltwi = sv.on_command("删除推特", aliases={"取消推特", "sctt", 'dt'})


@deltwi
async def _(event: Event):
    uname = event.get_plaintext()
    try:
        uid, _, uname = await lookup_user(uname)
    except:
        sv.logger.exception(f"获取{uname} 推特失败")
        await addtwi.finish(f"获取{uname} 推特失败")
    row = db.delete().where(db.gid == event.group_id, db.uid == uid).execute()
    if row:
        await deltwi.finish(f"{uname} 删除推特成功")
    else:
        await deltwi.finish(f"{uname} 删除推特失败")

BANWORDS = {"少妇","sm","SM","绿帽","约炮","必备","刺激","女神"}

@scheduled_job("interval", id="推特推送", minutes=3, jitter=25)
async def _():
    groups = await sv.get_enable_groups()
    for gid in groups:
        rows = db.select().where(db.gid == gid)
        if not rows:
            continue
        for row in rows:
            await asyncio.sleep(0.05)
            tid = row.tid
            uid = row.uid
            tws = await get_tweets(uid, tid)
            if not tws:
                continue
            for dyn in tws[::-1]:
                await asyncio.sleep(0.5)
                bot = groups[gid][0]
                # if dyn.media and all(kw not in dyn.text for kw in BANWORDS):
                pass
                try:
                    await bot.send_msg(group_id=gid, message=dyn.get_msg())
                    await asyncio.sleep(1)
                except Exception as e:
                    sv.logger.exception(e)
                db.replace(
                        gid=gid,
                        uid=uid,
                        tid=dyn.tid,
                        name=dyn.name,
                        uname=dyn.uname,
                        ).execute()

import os
import re
from hoshino.rule import keyword
from hoshino.util import get_event_imageurl, save_img
from nonebot.adapters.onebot.v11.event import MessageEvent
from nonebot.message import event_preprocessor
from nonebot.rule import Rule
from nonebot.typing import T_State

IMAGES = "IMAGES"
INFO = "INFO"
MSG = "MSG"


@event_preprocessor
async def _(bot: Bot, event: Event, state: T_State):
    if not isinstance(event, MessageEvent):
        return
    if not event.reply:
        return
    imgs = get_event_imageurl(event.reply)
    info = event.reply.sender.user_id
    tm = event.reply.time
    if imgs:
        state[IMAGES] = imgs
        state[INFO] = info, tm
    else:
        return
    msg = event.reply.message
    m = msg.extract_plain_text().strip()
    if m.startswith(("RandomTweet", "tweet@")) or "TID:" in m or "https://twitter.com/" in m:
        state[MSG] = m


async def is_img_reply(bot: Bot, event: Event, state: T_State):
    return IMAGES in state


async def is_twi_reply(bot: Bot, event: Event, state: T_State):
    return MSG in state


delimg = sv.on_command(
    "del", rule=Rule(is_img_reply, is_twi_reply), permission=SUPERUSER
)
addimg = sv.on_command(
    "save", rule=Rule(is_img_reply, is_twi_reply), permission=SUPERUSER
)
favimg = sv.on_command(
    "fav", rule=Rule(is_img_reply, is_twi_reply), permission=SUPERUSER
)
dell = sv.on_command("dell", aliases={"st", "删图"}, permission=SUPERUSER)
trace = sv.on_command(
    "trace",
    aliases={"zz", "追踪"},
    rule=Rule(is_img_reply, is_twi_reply),
    permission=SUPERUSER,
)
twistart = sv.on_startswith("tweet@", permission=SUPERUSER)
handlet = sv.on_message(
    False,
    False,
    SUPERUSER,
    priority=0,
    block=False,
    rule=keyword("TID:","https://twitter.com/",normal=False),
)
deletesth = sv.on_command("deletetwi", permission=SUPERUSER)


@dell.handle()
async def _(bot: Bot, event: Event):
    text = event.get_plaintext()
    if not text:
        return
    text = "tweet@" + text.replace("tweet@", "").replace(".jpg", "") + ".jpg"
    try:
        os.remove(img_dir + "/" + text)
        await delimg.send(f"图片{text}删除成功")
    except:
        await delimg.send(f"图片{text}删除失败")


comp = re.compile(r"([A-Za-z0-9_]{1,15})[:_]([0-9]*)_[0-9]")


@twistart
@trace.handle()
async def tra(bot: Bot, event: Event, state: T_State):
    msg = state.get(MSG, event.get_plaintext())
    c = await handle_twi_msg(msg, True)
    if c == 1:
        await trace.send(f"图像收藏成功")
    else:
        await trace.send(f"图像收藏失败")


fav = sv.on_command("kf", aliases={"kkf", "看看收藏"}, permission=SUPERUSER)


@fav.handle()
async def _(bot: Bot, event: Event, state: T_State):
    def get_node(m):
        c = MessageSegment("node", {"uin": bot.self_id, "name": "女菩萨bot", "content": m})
        return c

    msg = []
    for img in gen_imgs(0, True):
        m = f"{img.name}" + MessageSegment.image(img)
        msg.append(get_node(m))
    ls = len(msg)
    count, sup = divmod(ls, 50)
    msgs = []
    await bot.send(event, "收藏推特图的个数为：" + str(ls))
    await asyncio.sleep(0.3)
    for i in range(count):
        msgs.append(msg[i * 50 : i * 50 + 50])
    if sup != 0:
        msgs.append(msg[ls - sup :])
    for msg in msgs:
        await bot.call_api(
            "send_group_forward_msg", group_id=event.group_id, messages=msg
        )
        await asyncio.sleep(0.6)


@delimg.handle()
async def _(bot: Bot, event: Event, state: T_State):
    await delete_twi_msg(state[MSG])
    await delimg.send("推特图片删除成功")


async def delete_twi_msg(msg: str):
    if msg.startswith("RandomTweet"):
        text = msg.replace("RandomTweet", "").strip() + ".jpg"
        os.remove(os.path.abspath(img_dir + "/" + text))
        return 1
    else:
        return 0


async def handle_twi_msg(msg: str, fav: bool = False):
    if "TID:" in msg:
        text = msg.split("\n")[-1]
        tid = text.replace("TID: ", "")
        return await save_twi_img(tid, fav)
    elif "https://twitter.com/" in msg:
        text = msg.split("\n")[-1]
        tid = text.split("/status/")[-1]
        return await save_twi_img(tid, fav)
    elif msg.startswith(("RandomTweet", "tweet@")):
        te = (
            msg.replace("RandomTweet", "")
            .replace("tweet@", "")
            .replace(".jpg", "")
            .strip()
            + ".jpg"
        )
        mat = comp.match(te)
        if not mat:
            return 0
        tid = mat.group(2)
        return await save_twi_img(tid, fav)
    else:
        return 0


async def save_twi_img(tid: str, fav: bool = False):
    tid = tid.strip()
    tweet = await get_tweet(tid)
    if not tweet:
        return 3
    iname = f"tweet@{tweet.uname}:{tweet.tid}"
    ct = 0
    for i, img in enumerate(tweet.media):
        if img.startswith("file://") and fav:
            path = img.replace("file://", "")
            copy(path, fav_dir)
            ct += 1
            continue
        name = f"{iname}_{i}.jpg"
        for k in range(3):
            try:
                await save_img(img, name, fav)
                ct += 1
                break
            except Exception as e:
                sv.logger.exception(e)
            await asyncio.sleep(0.2)
    await addimg.send(tweet.get_msg())
    if ct == len(tweet.media):
        return 1
    return 2


@addimg.handle()
async def _(bot: Bot, event: Event, state: T_State):
    if await handle_twi_msg(state[MSG]) == 1:
        await addimg.send("推特图片保存成功")
    else:
        await addimg.send("推特图片获取失败")


@favimg.handle()
async def _(bot: Bot, event: Event, state: T_State):
    c = await handle_twi_msg(state[MSG], True)
    sv.logger.info(c)
    if c == 1:
        await addimg.send("推特图片收藏成功")
    else:
        await addimg.send("推特图片收藏失败")


@handlet
async def _(bot: Bot, event: Event):
    msg = event.get_plaintext()
    c = await handle_twi_msg(msg, True)
    if c == 1:
        await addimg.send("推特图片保存成功")
    elif c == 2:
        await addimg.send("推特图片获取失败")


@deletesth
async def _(bot: Bot, event: Event):
    rows = db.select().where(db.gid == event.group_id)
    if not rows:
        return
    rows = list(rows)
    al = rows[:50]
    for row in al:
        r = db.delete().where(db.gid == event.group_id, db.uid == row.uid).execute()
        if r:
            await bot.send(event, f"推特{row.uname} + {row.name} 删除成功")
            await asyncio.sleep(0.5)

@sv.on_command("deleteimg", permission=SUPERUSER)
async def _():
    img_d = Path(img_dir)
    imgs = [i for i in img_d.iterdir()]
    imgs.sort(key=sort_key)
    rmlen = len(imgs)//2
    for img in imgs[:rmlen]:
        os.remove(img)
    await addtwi.send("1/2 img dir删除成功")

@sv.on_command('updatetwi', permission=SUPERUSER)
async def _(event:Event):
    rows = db.select().where(db.gid == event.group_id)
    cnt = 0
    lr = len(rows)
    if not rows:
        return
    for r in rows:
        tid = await get_new_tweetid(r.uid)
        if not tid:
            await addtwi.send(f'{r.uname} {r.name}失效')
            await asyncio.sleep(.4)
            continue
        db.replace(uid=r.uid, gid=event.group_id, tid=tid).execute()
        await asyncio.sleep(.2)
    await addtwi.send(f'更新了{cnt}个twi，{lr-cnt}个推更新失败或失效')