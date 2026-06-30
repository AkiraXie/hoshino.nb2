# Thanks to https://github.com/MountainDash/nonebot-bison

import asyncio
from datetime import datetime
import time
from hoshino.platform import (
    GroupID,
    MessageID,
    PlainText,
    UniMessage,
    dump_target,
    group_target,
)
from hoshino.permission import SUPERUSER
from hoshino.permission import ADMIN
from hoshino.util import (
    send_segments,
    random_image_or_video_by_path,
)
from .db import (
    add_or_update_subscription,
    get_group_config,
    list_group_subscriptions,
    list_group_subscriptions_by_name,
    list_group_subscriptions_by_uid,
    list_subscriptions_by_name,
    list_subscriptions_by_uid,
    remove_group_subscriptions_by_name,
    remove_group_subscriptions_by_uid,
    update_group_config,
)
from .sub import uid_manager
from .sv import sv
from .internal.post_runtime import (
    render_messages,
    weibo_img_dir,
    weibo_video_dir,
)
from .request import (
    get_weibo_new,
)
from . import fav as _fav  # noqa: F401
from . import resolve as _resolve  # noqa: F401
import re
from nonebot.typing import T_State


def format_weibo_config_bits(group_id: int) -> str:
    config = get_group_config(group_id)
    return f"{config.only_pic}{config.send_screenshot}{config.send_segments}"


def format_weibo_config_message(group_id: int, *, editable: bool) -> str:
    bits = format_weibo_config_bits(group_id)
    message = (
        "当前微博推送配置: "
        f"{bits}\n"
        "位序: only_pic send_screenshot send_segments\n"
        "含义: 1=开 0=关"
    )
    if editable:
        message += "\n请发送 3 位二进制配置，例如 011"
    return message


configwb = sv.on_command(
    "configwb",
    aliases=("wbconfig"),
    permission=ADMIN,
)

showconfigwb = sv.on_command(
    "showconfigwb",
    aliases=("wbshowconfig"),
    permission=ADMIN,
)


@configwb.handle()
async def show_weibo_config(gid: int | None = GroupID()):
    if gid is None:
        await UniMessage.text("请在群聊中使用").send()
        return
    await UniMessage.text(format_weibo_config_message(gid, editable=True)).send()


@showconfigwb.handle()
async def show_weibo_config_readonly(gid: int | None = GroupID()):
    if gid is None:
        await showconfigwb.finish("请在群聊中使用")
        return
    await showconfigwb.finish(format_weibo_config_message(gid, editable=False))


@configwb.got("config_bits")
async def set_weibo_config(state: T_State, gid: int | None = GroupID()):
    if gid is None:
        await configwb.finish("请在群聊中使用")
        return
    config_bits = str(state["config_bits"]).strip()
    if not re.fullmatch(r"[01]{3}", config_bits):
        current_bits = format_weibo_config_bits(gid)
        await configwb.reject(
            "输入格式错误，请发送 3 位二进制，例如 011\n"
            f"当前配置仍为: {current_bits}\n"
            "位序: only_pic send_screenshot send_segments"
        )

    only_pic, send_screenshot, send_segments = (int(bit) for bit in config_bits)
    update_group_config(
        gid,
        only_pic=only_pic,
        send_screenshot=send_screenshot,
        send_segments=send_segments,
    )
    await configwb.finish(
        "微博推送配置已更新: "
        f"{config_bits}\n"
        f"only_pic={only_pic}, send_screenshot={send_screenshot}, send_segments={send_segments}"
    )


@sv.on_command(
    "微博随图",
    aliases=("wbimg", "wim"),
    only_group=False,
    only_to_me=True,
    permission=SUPERUSER,
    priority=5,
)
async def weibo_random_image(
    text: str = PlainText(),
    message_id: int | None = MessageID(),
):
    path = weibo_img_dir
    num = 12
    text = text.strip()
    texts = text.split(maxsplit=1)
    keyword = None
    if len(texts) == 2:
        keyword, num_str = texts
        if num_str.isdigit():
            num = int(num_str)
        else:
            keyword = keyword + num_str
    elif len(texts) == 1:
        keyword = texts[0]
        if keyword.isdigit():
            num = int(keyword)
    seed = time.time() + (message_id or 0)
    imgs = random_image_or_video_by_path(
        path, num=num, seed=seed, video=False, keyword=keyword
    )
    await send_segments(imgs)


@sv.on_command(
    "微博随影",
    aliases=("wbvid", "wvi"),
    only_to_me=True,
    only_group=False,
    permission=SUPERUSER,
    priority=5,
)
async def weibo_random_video(
    text: str = PlainText(),
    message_id: int | None = MessageID(),
):
    path = weibo_video_dir
    num = 2
    text = text.strip()
    texts = text.split(maxsplit=1)
    keyword = None
    if len(texts) == 2:
        keyword, num_str = texts
        if num_str.isdigit():
            num = int(num_str)
        else:
            keyword = keyword + num_str
    elif len(texts) == 1:
        keyword = texts[0]
        if keyword.isdigit():
            num = int(keyword)
    seed = time.time() + (message_id or 0)
    imgs = random_image_or_video_by_path(
        path, num=num, seed=seed, video=True, keyword=keyword
    )
    await send_segments(imgs)


@sv.on_command(
    "添加微博订阅",
    aliases=("订阅微博", "新增微博", "添加微博", "添加weibo", "addweibo", "addwb"),
)
async def add_subscription(gid: int | None = GroupID(), msg: str = PlainText()):
    if gid is None:
        await UniMessage.text("请在群聊中使用").send()
        return
    target_data = dump_target(group_target(gid))
    msg = msg.strip()
    keywords = []
    try:
        msg = msg.split(" ")
        if len(msg) == 1:
            uid = msg[0]
        else:
            uid = msg[0]
            keywords = msg[1:]
        if not uid.isdecimal():
            match = re.search(r"weibo\.com\/(u\/)?(\d+)", uid)
            if match:
                uid = match.group(2)
            else:
                await UniMessage.text("无效的UID格式，请输入数字ID或完整的微博个人主页链接").send()
                return
        post = await get_weibo_new(uid, ts=0)
        if not post:
            await UniMessage.text(f"无法获取微博用户信息，UID: {uid}").send()
            return
    except Exception as e:
        sv.logger.exception(e)
        await UniMessage.text(f"无法获取微博用户信息，UID: {uid}").send()
        return
    kw = "-_-".join(keywords) if keywords else ""
    ts = time.time()
    add_or_update_subscription(gid, uid, post.nickname, ts, kw, target_data)
    await uid_manager.add_uid(uid)
    if keywords:
        await UniMessage.text(f"成功订阅微博用户：{post.nickname} UID: {uid} 关键词: {kw}").send()
    else:
        await UniMessage.text(f"成功订阅微博用户：{post.nickname} UID: {uid}").send()


@sv.on_command(
    "删除微博订阅", aliases=("取消微博", "删除微博", "rmweibo", "删除weibo", "rmwb")
)
async def remove_subscription(gid: int | None = GroupID(), uids: str = PlainText()):
    if gid is None:
        await UniMessage.text("请在群聊中使用").send()
        return
    uids = uids.strip()
    uids = uids.split()
    for uid in uids:
        await asyncio.sleep(0.3)
        if uid.isdecimal():
            num = remove_group_subscriptions_by_uid(gid, uid)
            if num:
                await uid_manager.remove_uid(
                    uid, lambda u: bool(list_subscriptions_by_uid(u))
                )
        else:
            num, target_uid = remove_group_subscriptions_by_name(gid, uid)
            if num and target_uid:
                await uid_manager.remove_uid(
                    target_uid,
                    lambda u: bool(list_subscriptions_by_uid(u)),
                )
        if num:
            await UniMessage.text(f"{uid} 删除微博订阅成功").send()
        else:
            await UniMessage.text(f"{uid} 删除微博订阅失败").send()


@sv.on_command("微博订阅", aliases=("微博订阅列表", "lookweibo", "lswb", "listweibo"))
async def list_subscriptions(gid: int | None = GroupID()):
    if gid is None:
        await UniMessage.text("请在群聊中使用").send()
        return
    rows = list_group_subscriptions(gid)
    if not rows:
        await UniMessage.text("本群没有订阅微博用户").send()
        return
    msg = "当前订阅的微博用户：\n"
    for i, row in enumerate(rows):
        uid = row.uid
        name = row.name
        ts = datetime.fromtimestamp(row.time).strftime("%Y-%m-%d %H:%M:%S")
        msg += f"{i + 1}. UID: {uid}, 昵称: {name}, 上次更新时间: {ts}\n"
    await UniMessage.text(msg).send()


@sv.on_command("微博最新订阅", aliases=("查看微博最新", "seeweibo", "kkwb", "seewb"))
async def see_weibo(gid: int | None = GroupID(), arg: str = PlainText()):
    if gid is None:
        await UniMessage.text("请在群聊中使用").send()
        return
    arg = arg.strip()
    if arg.isdecimal():
        rows = list_group_subscriptions_by_uid(gid, arg)
    else:
        rows = list_group_subscriptions_by_name(gid, arg)
    if not rows:
        await UniMessage.text(f"没有订阅{arg}微博").send()
    else:
        uid = rows[0].uid
        keywords = rows[0].keyword
        if keywords:
            keywords = keywords.split("-_-")
        else:
            keywords = []
        post = await get_weibo_new(uid, 0)
        if not post:
            await UniMessage.text(f"没有获取到{arg}微博").send()
            return
        post_message = await post.get_message()
        msgs = render_messages(post_message, post=post)
        await send_segments(msgs)


@sv.on_command(
    "查库微博",
    aliases=("wbquery", "微博查库"),
    permission=SUPERUSER,
    only_group=False,
    only_to_me=True,
)
async def query_weibo_user(arg: str = PlainText()):
    arg = arg.strip()
    if arg.isdecimal():
        rows = list_subscriptions_by_uid(arg)
    else:
        rows = list_subscriptions_by_name(arg)
    if not rows:
        await UniMessage.text(f"没有查到微博用户 {arg}").send()
        return
    msg = "微博用户信息:\n"
    for row in rows:
        msg += (
            f"UID: {row.uid}, 昵称: {row.name}, 关键词: {row.keyword or '无'}, "
            f"上次更新时间: {datetime.fromtimestamp(row.time).strftime('%Y-%m-%d %H:%M:%S')}\n"
        )
        break
    await UniMessage.text(msg).send()
