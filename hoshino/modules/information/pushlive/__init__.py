import asyncio
from datetime import datetime

from hoshino import Bot, Event, Service, on_startup
from hoshino.schedule import scheduled_job

from .db import (
    LiveSub,
    add_subscription,
    list_all_room_ids,
    list_group_subscriptions,
    list_subscriptions_by_room,
    remove_group_subscription,
    remove_group_subscription_by_name,
)
from .model import LiveInfo
from ..utils import UIDManager

sv = Service("pushlive", enable_on_default=False, visible=False)

# (room_id, platform) -> 开播时刻，None 表示未开播
_live_status: dict[tuple[str, str], datetime | None] = {}

# 使用 UIDManager 轮询直播间，每次只检查一个
room_manager = UIDManager()
room_manager._min_interval = 30  # 同一直播间最短轮询间隔
room_manager._cold_min_interval = 300


def _room_key(room_id: str, platform: str) -> str:
    """编码 (room_id, platform) 为 UIDManager 使用的字符串 key"""
    return f"{room_id}:{platform}"


def _parse_room_key(key: str) -> tuple[str, str]:
    """从 key 解码回 (room_id, platform)"""
    room_id, platform = key.rsplit(":", 1)
    return room_id, platform

# 平台别名映射
PLATFORM_ALIASES: dict[str, str] = {
    "bilibili": "bilibili",
    "b站": "bilibili",
    "bili": "bilibili",
    "斗鱼": "douyu",
    "douyu": "douyu",
}

PLATFORM_DISPLAY: dict[str, str] = {
    "bilibili": "B站",
    "douyu": "斗鱼",
}


def parse_room_input(text: str) -> tuple[str, str]:
    """解析 room_id:platform 格式，默认 bilibili"""
    for sep in (":", "："):
        if sep in text:
            room_id, plat_raw = text.rsplit(sep, 1)
            platform = PLATFORM_ALIASES.get(plat_raw.strip().lower(), plat_raw.strip().lower())
            return room_id.strip(), platform
    return text.strip(), "bilibili"


def parse_platform_filter(text: str) -> str | None:
    """解析平台过滤参数"""
    text = text.strip()
    if not text:
        return None
    if text.startswith(":") or text.startswith("："):
        text = text[1:].strip()
    if not text:
        return None
    return PLATFORM_ALIASES.get(text.lower(), text.lower())


async def get_room_status(room_id: str, platform: str) -> LiveInfo:
    """根据平台分发获取直播间状态"""
    if platform == "douyu":
        from .douyu import get_room_status as _get
    else:
        from .bilibili import get_room_status as _get
    res = await _get(room_id)
    return res

def _format_live_duration(show_time: datetime | None) -> str:
    """根据开播时间计算并格式化直播时长"""
    if not show_time:
        return ""
    delta = datetime.now() - show_time
    total_seconds = int(delta.total_seconds())
    if total_seconds < 0:
        return ""
    hours, remainder = divmod(total_seconds, 3600)
    minutes, _ = divmod(remainder, 60)
    if hours > 0:
        return f"{hours}小时{minutes}分钟"
    return f"{minutes}分钟"


# ==================== 推送循环 ====================


@on_startup
async def _init_live_status():
    """启动时初始化所有已订阅直播间的状态，并填充 room_manager"""
    room_ids = list_all_room_ids()
    keys = [_room_key(room_id, platform) for room_id, platform in room_ids]
    await room_manager.init(keys,120,600)

    for room_id, platform in room_ids:
        try:
            info = await get_room_status(room_id, platform)
            _live_status[(room_id, platform)] = info.show_time if info.show_status == 1 else None
            sv.logger.info(f"初始化直播间 {room_id}({platform}) 状态: {info.show_status} {info.show_time}")
        except Exception as e:
            sv.logger.error(f"初始化直播间 {room_id}({platform}) 状态失败: {e}")
        await asyncio.sleep(0.5)


@scheduled_job("interval", seconds=3, jitter=1, id="直播推送")
async def check_live_updates():
    if room_manager.get_count() == 0:
        return

    key = await room_manager.get_next_uid()
    if not key:
        return

    room_id, platform = _parse_room_key(key)
    success = False
    try:
        info = await get_room_status(room_id, platform)
        old_time = _live_status.get((room_id, platform))
        was_live = old_time is not None
        is_live = info.show_status == 1

        if is_live:
            if not was_live:
                _live_status[(room_id, platform)] = info.show_time or datetime.now()
        else:
            if was_live:
                _live_status[(room_id, platform)] = None

        if was_live != is_live:
            await _dispatch_status_change(room_id, platform, info, old_time)
        success = True
    except Exception as e:
        sv.logger.error(f"检查直播间 {room_id}({platform}) 失败: {e}")
    finally:
        await room_manager.finish_processing(key, success)


async def _dispatch_status_change(room_id: str, platform: str, info: LiveInfo, old_time: datetime | None = None):
    """向所有订阅了该直播间的群推送状态变化"""
    subs = list_subscriptions_by_room(room_id, platform)
    if not subs:
        return

    plat_name = PLATFORM_DISPLAY.get(platform, platform)

    if info.show_status == 1:
        text = f"🔴 [{plat_name}] {info.anchor} 开播了！\n标题: {info.title}\n{info.url}"
        from hoshino import MessageSegment, Message

        msg_parts = [Message(text)]
        if info.cover:
            msg_parts.append(MessageSegment.image(info.cover))
    else:
        duration = _format_live_duration(old_time) if old_time else ""
        duration_text = f"  本次直播: {duration}" if duration else ""
        text = f"⚪ [{plat_name}] {info.anchor} 下播了{duration_text}\n{info.url}"
        from hoshino import Message

        msg_parts = [Message(text)]

    # 获取所有已启用该服务的群
    enabled_groups = await sv.get_enable_groups()
    target_groups = {sub.group for sub in subs}

    for gid in target_groups:
        if gid not in enabled_groups:
            continue
        bots = enabled_groups[gid]
        for bot in bots:
            try:
                for msg in msg_parts:
                    await bot.send_group_msg(group_id=gid, message=msg)
                    await asyncio.sleep(0.3)
                sv.logger.info(f"直播推送 {info.anchor}({room_id}/{platform}) -> 群{gid} 成功")
            except Exception as e:
                sv.logger.error(f"直播推送 {info.anchor}({room_id}/{platform}) -> 群{gid} 失败: {e}")
            break  # 一个群只用一个 bot 发


# ==================== 命令 ====================


@sv.on_command("添加直播订阅", aliases=("订阅直播", "添加直播", "addbililive", "adblive", "addlive"))
async def cmd_add_live(bot: Bot, event: Event):
    gid = event.group_id
    msg = event.get_plaintext().strip()
    if not msg:
        await bot.send(event, "用法: 添加直播订阅 房间号[:平台]\n平台: bilibili(默认), douyu/斗鱼")
        return

    room_id, platform = parse_room_input(msg.split()[0])
    if not room_id.isdecimal():
        await bot.send(event, "请输入有效的直播间号（纯数字）")
        return

    if platform not in PLATFORM_DISPLAY:
        await bot.send(event, f"不支持的平台: {platform}\n支持: bilibili, douyu/斗鱼")
        return

    plat_name = PLATFORM_DISPLAY[platform]

    try:
        info = await get_room_status(room_id, platform)
        if not info.anchor:
            await bot.send(event, f"无法获取 [{plat_name}] 直播间 {room_id} 的主播信息")
            return
    except Exception as e:
        sv.logger.exception(e)
        await bot.send(event, f"获取 [{plat_name}] 直播间信息失败: {room_id}")
        return
    
    add_subscription(gid, room_id, info.anchor, platform)
    await room_manager.add_uid(_room_key(room_id, platform))
    if (room_id, platform) not in _live_status:
        _live_status[(room_id, platform)] = (info.show_time or datetime.now()) if info.show_status == 1 else None
    reply = f"成功订阅 [{plat_name}] 直播间: {info.anchor} (房间号: {room_id})"
    if info.show_status == 1:
        start_time = _live_status.get((room_id, platform))
        duration = _format_live_duration(start_time) if start_time else ""
        reply += f"\n🔴 当前直播中"
        if info.title:
            reply += f"  标题: {info.title}"
        if duration:
            reply += f"  已播: {duration}"
    await bot.send(event, reply)


@sv.on_command("删除直播订阅", aliases=("取消直播", "删除直播", "rmbililive", "rmblive", "rmlive"))
async def cmd_remove_live(bot: Bot, event: Event):
    gid = event.group_id
    args = event.get_plaintext().strip().split()
    if not args:
        await bot.send(event, "用法: 删除直播订阅 房间号[:平台]/主播名[:平台]")
        return

    for arg in args:
        has_platform = ":" in arg or "：" in arg
        room_id_or_name, platform = parse_room_input(arg)

        if room_id_or_name.isdecimal():
            num = remove_group_subscription(gid, room_id_or_name, platform)
            if num and not list_subscriptions_by_room(room_id_or_name, platform):
                _live_status.pop((room_id_or_name, platform), None)
                await room_manager.remove_uid(
                    _room_key(room_id_or_name, platform),
                    lambda k: bool(list_subscriptions_by_room(*_parse_room_key(k))),
                )
        else:
            plat_filter = platform if has_platform else None
            num, target_room, target_plat = remove_group_subscription_by_name(gid, room_id_or_name, plat_filter)
            if num and target_room and target_plat and not list_subscriptions_by_room(target_room, target_plat):
                _live_status.pop((target_room, target_plat), None)
                await room_manager.remove_uid(
                    _room_key(target_room, target_plat),
                    lambda k: bool(list_subscriptions_by_room(*_parse_room_key(k))),
                )

        if num:
            await bot.send(event, f"{arg} 删除直播订阅成功")
        else:
            await bot.send(event, f"{arg} 删除直播订阅失败（未找到）")

        await asyncio.sleep(0.3)


@sv.on_command("直播订阅", aliases=("直播订阅列表", "lsbililive", "lsblive", "listbililive", "lslive"))
async def cmd_list_live(bot: Bot, event: Event):
    gid = event.group_id
    filter_text = event.get_plaintext().strip()
    plat_filter = parse_platform_filter(filter_text)

    rows = list_group_subscriptions(gid, plat_filter)
    if not rows:
        if plat_filter:
            await bot.send(event, f"本群没有 [{PLATFORM_DISPLAY.get(plat_filter, plat_filter)}] 的直播订阅")
        else:
            await bot.send(event, "本群没有订阅直播间")
        return

    # 按平台分组
    from collections import defaultdict
    grouped: dict[str, list[LiveSub]] = defaultdict(list)
    for row in rows:
        grouped[row.platform].append(row)

    lines = ["当前订阅的直播间:"]
    # 按 PLATFORM_DISPLAY 顺序排列，未知平台排最后
    platform_order = list(PLATFORM_DISPLAY.keys())
    sorted_platforms = sorted(grouped.keys(), key=lambda p: (platform_order.index(p) if p in platform_order else len(platform_order)))

    for plat in sorted_platforms:
        plat_name = PLATFORM_DISPLAY.get(plat, plat)
        for row in grouped[plat]:
            start_time = _live_status.get((row.room_id, row.platform))
            if start_time is not None:
                duration = _format_live_duration(start_time)
                status_text = f"🔴直播中({duration})" if duration else "🔴直播中"
            else:
                status_text = "⚪未开播"
            lines.append(f"[{plat_name}] {row.name} (房间号: {row.room_id}) {status_text}")
    await bot.send(event, "\n".join(lines))


@sv.on_command("直播状态", aliases=("查看直播", "checkbililive", "ckblive", "checklive"))
async def cmd_check_live(bot: Bot, event: Event):
    arg = event.get_plaintext().strip()
    if not arg:
        await bot.send(event, "用法: 直播状态 房间号[:平台]")
        return

    room_id, platform = parse_room_input(arg.split()[0])
    plat_name = PLATFORM_DISPLAY.get(platform, platform)

    try:
        info = await get_room_status(room_id, platform)
    except Exception as e:
        sv.logger.error(f"查询直播间 {room_id}({platform}) 失败: {e}")
        await bot.send(event, f"查询 [{plat_name}] 直播间 {room_id} 失败")
        return

    if info.show_status == 1:
        duration = _format_live_duration(info.show_time) if info.show_time else ""
        duration_text = f"\n已播: {duration}" if duration else ""
        await bot.send(event, f"🔴 [{plat_name}] {info.anchor} 直播中\n标题: {info.title}{duration_text}\n{info.url}")
    else:
        await bot.send(event, f"⚪ [{plat_name}] {info.anchor} 未开播\n{info.url}")
