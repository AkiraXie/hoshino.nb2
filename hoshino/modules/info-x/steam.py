"""Cross-adapter Steam playing-state subscriptions."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import nonebot
from loguru import logger
from lxml import etree
from nonebot.adapters import Bot

from hoshino import db_dir
from hoshino.command import MsgTarget, UniMessage
from hoshino.core.hooks import on_serial_startup
from hoshino.core.schedule import scheduled_job
from hoshino.platform import (
    dump_target,
    group_scope_key,
    group_target,
    load_target,
    platform_key,
    send_to_target,
    target_scope_key,
)
from hoshino.platform.depends import ParamText
from hoshino.platform.permission import ADMIN
from hoshino.service import Service
from hoshino.util import aiohttpx


sv = Service("steam", enable_on_default=False, visible=False)
subscribe_file = db_dir / "subscribes.json"
sub: dict[str, Any] = {"version": 2, "subscribes": {}}
playing_state: dict[str, dict[str, str]] = {}


def get_steam_api_key() -> str | None:
    key = sv.get_config().get("key")
    return str(key) if key else None


def _subscription(bot: Bot, target: MsgTarget) -> dict[str, Any]:
    platform = platform_key(bot)
    group_id = int(target.parent_id or target.id)
    return {
        "scope_key": target_scope_key(target, platform=platform),
        "platform": platform,
        "group_id": group_id,
        "target_data": dump_target(target),
    }


def _load_subscriptions() -> bool:
    global sub
    if not subscribe_file.exists():
        return False
    try:
        raw = json.loads(subscribe_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.exception("Failed to load Steam subscriptions")
        return False
    subscribes = raw.get("subscribes", {}) if isinstance(raw, dict) else {}
    migrated = False
    normalized: dict[str, list[dict[str, Any]]] = {}
    for steam_id, entries in subscribes.items():
        targets: list[dict[str, Any]] = []
        for entry in entries if isinstance(entries, list) else []:
            if isinstance(entry, dict) and entry.get("scope_key"):
                targets.append(entry)
                continue
            if isinstance(entry, (int, str)) and str(entry).lstrip("-").isdigit():
                group_id = int(entry)
                targets.append(
                    {
                        "scope_key": group_scope_key(group_id, platform="ob11"),
                        "platform": "ob11",
                        "group_id": group_id,
                        "target_data": dump_target(group_target(group_id)),
                    }
                )
                migrated = True
        normalized[str(steam_id)] = targets
    sub = {"version": 2, "subscribes": normalized}
    return migrated


def _save_subscriptions() -> None:
    subscribe_file.parent.mkdir(parents=True, exist_ok=True)
    temporary = subscribe_file.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(sub, indent=4, ensure_ascii=False), encoding="utf-8"
    )
    temporary.replace(subscribe_file)


@on_serial_startup
async def initialize_steam_subscriptions() -> None:
    if _load_subscriptions() or not subscribe_file.exists():
        _save_subscriptions()


async def format_id(account: str) -> str:
    if account.startswith("7656") and len(account) == 17 and account.isdigit():
        return account
    response = await aiohttpx.get(f"https://steamcommunity.com/id/{account}?xml=1")
    xml = etree.XML(response.content)
    values = xml.xpath("/profile/steamID64")
    if not values or not values[0].text:
        raise ValueError("Steam account was not found")
    return str(values[0].text)


adds = sv.on_command("添加steam订阅", permission=ADMIN)
dels = sv.on_command("取消steam订阅", permission=ADMIN)
looks = sv.on_command(
    "steam订阅列表",
    aliases=(
        "查看本群steam",
        "本群steam订阅",
        "steam列表",
        "谁在玩游戏",
        "看看steam",
        "kksteam",
    ),
)
look = sv.on_command(
    "查询steam账号", permission=ADMIN, aliases=("查看steam", "查看steam订阅")
)


@adds.handle()
async def handle_add(bot: Bot, target: MsgTarget, text: str = ParamText()) -> None:
    try:
        status = await get_account_status(text.strip())
        await update_steam_ids(text.strip(), _subscription(bot, target))
    except Exception as exc:
        logger.opt(exception=exc).error("Failed to add Steam subscription")
        await UniMessage.text("订阅失败").send()
        return
    if status["personaname"]:
        game = status["gameextrainfo"] or "当前没有运行游戏"
        await UniMessage.text(f"{status['personaname']}：{game}\n订阅成功").send()
    else:
        await UniMessage.text("查询失败").send()


@dels.handle()
async def handle_remove(bot: Bot, target: MsgTarget, text: str = ParamText()) -> None:
    try:
        removed = await del_steam_ids(text.strip(), _subscription(bot, target))
    except Exception as exc:
        logger.opt(exception=exc).error("Failed to remove Steam subscription")
        await UniMessage.text("删除订阅失败").send()
        return
    await UniMessage.text("删除订阅成功" if removed else "未找到该订阅").send()


@looks.handle()
async def handle_list(bot: Bot, target: MsgTarget) -> None:
    scope_key = target_scope_key(target, platform=platform_key(bot))
    await update_game_status()
    lines = ["======steam======"]
    for steam_id, status in playing_state.items():
        entries = sub["subscribes"].get(steam_id, [])
        if any(item.get("scope_key") == scope_key for item in entries):
            game = status["gameextrainfo"]
            lines.append(
                f"{status['personaname']} 正在游玩 {game}"
                if game
                else f"{status['personaname']} 没在玩游戏"
            )
    await UniMessage.text("\n".join(lines) + "\n").send()


@look.handle()
async def handle_lookup(text: str = ParamText()) -> None:
    status = await get_account_status(text.strip())
    if not status["personaname"]:
        await UniMessage.text("查询失败！").send()
    elif not status["gameextrainfo"]:
        await UniMessage.text(f"{status['personaname']} 没在玩游戏！").send()
    else:
        await UniMessage.text(
            f"{status['personaname']} 正在玩 {status['gameextrainfo']}！"
        ).send()


async def get_account_status(account: str) -> dict[str, str]:
    key = get_steam_api_key()
    if key is None:
        return {"personaname": "", "gameextrainfo": ""}
    steam_id = await format_id(account)
    response = await aiohttpx.get(
        "https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v0002/",
        params={"key": key, "format": "json", "steamids": steam_id},
    )
    if not response.ok:
        raise RuntimeError(f"Steam API returned {response.status_code}")
    players = response.json.get("response", {}).get("players", [])
    if not players:
        return {"personaname": "", "gameextrainfo": ""}
    player = players[0]
    return {
        "personaname": str(player.get("personaname", "")),
        "gameextrainfo": str(player.get("gameextrainfo", "")),
    }


async def update_game_status(api_key: str | None = None) -> None:
    subscribes = sub["subscribes"]
    if not subscribes or not (api_key := api_key or get_steam_api_key()):
        return
    response = await aiohttpx.get(
        "https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v0002/",
        params={
            "key": api_key,
            "format": "json",
            "steamids": ",".join(subscribes),
        },
    )
    if not response.ok:
        raise RuntimeError(f"Steam API returned {response.status_code}")
    for player in response.json.get("response", {}).get("players", []):
        playing_state[str(player["steamid"])] = {
            "personaname": str(player.get("personaname", "")),
            "gameextrainfo": str(player.get("gameextrainfo", "")),
        }


async def update_steam_ids(steam_id: str, subscription: dict[str, Any]) -> bool:
    normalized = await format_id(steam_id)
    entries = sub["subscribes"].setdefault(normalized, [])
    if any(item.get("scope_key") == subscription["scope_key"] for item in entries):
        return False
    entries.append(subscription)
    _save_subscriptions()
    await update_game_status()
    return True


async def del_steam_ids(steam_id: str, subscription: dict[str, Any]) -> bool:
    normalized = await format_id(steam_id)
    entries = sub["subscribes"].get(normalized, [])
    remaining = [
        item for item in entries if item.get("scope_key") != subscription["scope_key"]
    ]
    if len(remaining) == len(entries):
        return False
    if remaining:
        sub["subscribes"][normalized] = remaining
    else:
        sub["subscribes"].pop(normalized, None)
        playing_state.pop(normalized, None)
    _save_subscriptions()
    return True


@scheduled_job("cron", minute="*/2", id="推送steam", jitter=10)
async def check_steam_status() -> None:
    api_key = get_steam_api_key()
    if api_key is None:
        return
    if not playing_state:
        await update_game_status(api_key)
        return
    old_state = {key: value.copy() for key, value in playing_state.items()}
    await update_game_status(api_key)
    for steam_id, status in playing_state.items():
        old = old_state.get(steam_id)
        if old is None or status["gameextrainfo"] == old["gameextrainfo"]:
            continue
        if status["gameextrainfo"]:
            message = f"{status['personaname']} 开始游玩 {status['gameextrainfo']}！"
        else:
            message = f"{status['personaname']} 不玩 {old['gameextrainfo']} 了！"
        await _broadcast(sub["subscribes"].get(steam_id, []), message)


async def _broadcast(subscriptions: list[dict[str, Any]], message: str) -> None:
    bots = list(nonebot.get_bots().values())
    for subscription in subscriptions:
        scope_key = str(subscription["scope_key"])
        if not sv.check_enabled(scope_key):
            continue
        bot = next(
            (item for item in bots if platform_key(item) == subscription["platform"]),
            None,
        )
        if bot is None:
            continue
        try:
            await send_to_target(bot, load_target(subscription["target_data"]), message)
        except Exception as exc:
            logger.opt(exception=exc).error(
                "Failed to send Steam update to {}", scope_key
            )
        await asyncio.sleep(0.5)


_load_subscriptions()


__all__ = [
    "check_steam_status",
    "del_steam_ids",
    "get_account_status",
    "get_steam_api_key",
    "playing_state",
    "sub",
    "sv",
    "update_game_status",
    "update_steam_ids",
]
