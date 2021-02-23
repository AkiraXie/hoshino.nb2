from typing import Iterable
from loguru import logger
from lxml import etree
import json
import os
from hoshino import scheduled_job, Bot, Event, Service
from asyncio import sleep
from hoshino.util import get_bot_list, aiohttpx

sv = Service("steam", enable_on_default=False, visible=False)

subscribe_file = os.path.join(os.path.dirname(__file__), 'subscribes.json')
with open(subscribe_file, mode="r") as f:
    f = f.read()
    sub = json.loads(f)
cfg = sv.config

playing_state = {}


async def format_id(id: str) -> str:
    if id.startswith('76561198') and len(id) == 17:
        return id
    else:
        resp = await aiohttpx.get(f'https://steamcommunity.com/id/{id}?xml=1')
        xml = etree.XML(resp.content)
        return xml.xpath('/profile/steamID64')[0].text
adds = sv.on_command("添加steam订阅")
dels = sv.on_command("取消steam订阅")
looks = sv.on_command("steam订阅列表", aliases=('查看本群steam', '本群steam订阅', 'steam'))
look = sv.on_command("查询steam账号", aliases=('查看steam', '查看steam订阅'))


@adds.handle()
async def _(bot: Bot, event: Event):
    account = event.get_plaintext().strip()
    try:
        rsp = await get_account_status(account)
        if rsp["personaname"] == "":
            await bot.send(event, "查询失败！")
        elif rsp["gameextrainfo"] == "":
            await bot.send(event, f"%s 没在玩游戏！" % rsp["personaname"])
        else:
            await bot.send(event, f"%s 正在玩 %s ！" % (rsp["personaname"], rsp["gameextrainfo"]))
        await update_steam_ids(account, event.group_id)
        await bot.send(event, "订阅成功")
    except Exception as e:
        logger.exception(e)
        await bot.send(event, "订阅失败")


@dels.handle()
async def _(bot: Bot, event: Event):
    account = event.get_plaintext().strip()
    try:
        await del_steam_ids(account, event.group_id)
        await bot.send(event, "删除订阅成功")
    except Exception as e:
        logger.exception(e)
        await bot.send(event, "删除订阅失败")


@looks.handle()
async def _(bot: Bot, event: Event):
    group_id = event.group_id
    msg = '======steam======\n'
    await update_game_status()
    for key, val in playing_state.items():
        if group_id in sub["subscribes"][str(key)]:
            if val["gameextrainfo"] == "":
                msg += "%s 没在玩游戏\n" % val["personaname"]
            else:
                msg += "%s 正在游玩 %s\n" % (val["personaname"],
                                         val["gameextrainfo"])
    await bot.send(event, msg)


@look.handle()
async def _(bot: Bot, event: Event):
    account = event.get_plaintext()
    rsp = await get_account_status(account)
    if rsp["personaname"] == "":
        await bot.send(event, "查询失败！")
    elif rsp["gameextrainfo"] == "":
        await bot.send(event, f"%s 没在玩游戏！" % rsp["personaname"])
    else:
        await bot.send(event, f"%s 正在玩 %s ！" % (rsp["personaname"], rsp["gameextrainfo"]))


async def get_account_status(id) -> dict:
    id = await format_id(id)
    params = {
        "key": cfg["key"],
        "format": "json",
        "steamids": id
    }
    try:
        resp = await aiohttpx.get("https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v2/", params=params)
    except Exception as e:
        logger.exception(e)
        logger.error(type(e))
    rsp = resp.json
    friend = rsp["response"]["players"][0]
    return {
        "personaname": friend["personaname"] if "personaname" in friend else "",
        "gameextrainfo": friend["gameextrainfo"] if "gameextrainfo" in friend else ""
    }


async def update_game_status() -> None:
    params = {
        "key": cfg["key"],
        "format": "json",
        "steamids": ",".join(sub["subscribes"].keys())
    }
    try:
        resp = await aiohttpx.get("https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v2/", params=params)
    except Exception as e:
        logger.exception(e)
        logger.error(type(e))
    rsp = resp.json
    for friend in rsp["response"]["players"]:
        playing_state[friend["steamid"]] = {
            "personaname": friend["personaname"],
            "gameextrainfo": friend["gameextrainfo"] if "gameextrainfo" in friend else ""
        }


async def update_steam_ids(steam_id, group):
    steam_id = await format_id(steam_id)
    if steam_id not in sub["subscribes"]:
        sub["subscribes"][str(steam_id)] = []
    if group not in sub["subscribes"][str(steam_id)]:
        sub["subscribes"][str(steam_id)].append(group)
    with open(subscribe_file, mode="w") as fil:
        json.dump(sub, fil, indent=4, ensure_ascii=False)
    await update_game_status()


async def del_steam_ids(steam_id, group):
    steam_id = await format_id(steam_id)
    if group in sub["subscribes"][str(steam_id)]:
        sub["subscribes"][str(steam_id)].remove(group)
    with open(subscribe_file, mode="w") as fil:
        json.dump(sub, fil, indent=4, ensure_ascii=False)
    await update_game_status()


@scheduled_job('cron', minute='*/2', id='推送steam',jitter=20)
async def check_steam_status():
    old_state = playing_state.copy()
    await update_game_status()
    for key, val in playing_state.items():
        if val["gameextrainfo"] != old_state[key]["gameextrainfo"]:
            glist = set(sub["subscribes"][key]) & set((await sv.get_enable_groups()).keys())
            if val["gameextrainfo"] == "":
                await broadcast(glist,
                                "%s 不玩 %s 了！" % (val["personaname"], old_state[key]["gameextrainfo"]))
            else:
                await broadcast(glist,
                                "%s 开始游玩 %s ！" % (val["personaname"], val["gameextrainfo"]))


async def broadcast(group_list: Iterable, msg):
    for group in group_list:
        for bot in get_bot_list():
            await bot.send_group_msg(group_id=group, message=msg)
            await sleep(0.5)
