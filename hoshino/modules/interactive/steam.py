from typing import Iterable
from loguru import logger
from lxml import etree
import json
from nonebot.adapters import Bot
from hoshino.core.schedule import scheduled_job
from hoshino.service import Service
from hoshino import db_dir
from hoshino.platform.permission import ADMIN
from asyncio import sleep
from hoshino.util import aiohttpx
from hoshino.command import Alconna, Args, MsgTarget, UniMessage
from hoshino.platform import group_target, send_to_target

sv = Service("steam", enable_on_default=False, visible=False)
sub = {"subscribes": {}}
subscribe_file = db_dir / "subscribes.json"
if not subscribe_file.exists():
    with subscribe_file.open(mode="w") as f:
        json.dump(sub, f, indent=4, ensure_ascii=False)
with subscribe_file.open(mode="r") as f:
    f = f.read()
    sub = json.loads(f)
cfg = sv.get_config()

playing_state = {}


async def format_id(id: str) -> str:
    if id.startswith("7656") and len(id) == 17 and id.isdigit():
        return id
    else:
        resp = await aiohttpx.get(f"https://steamcommunity.com/id/{id}?xml=1")
        xml = etree.XML(resp.content)
        return xml.xpath("/profile/steamID64")[0].text


adds = sv.on_alconna(Alconna("添加steam订阅", Args["account", str]), permission=ADMIN)
dels = sv.on_alconna(Alconna("取消steam订阅", Args["account", str]), permission=ADMIN)
looks = sv.on_alconna(
    Alconna("steam订阅列表"),
    aliases=(
        "查看本群steam",
        "本群steam订阅",
        "steam列表",
        "谁在玩游戏",
        "看看steam",
        "kksteam",
    ),
)
look = sv.on_alconna(
    Alconna("查询steam账号", Args["account", str]),
    permission=ADMIN,
    aliases=("查看steam", "查看steam订阅"),
)


def _group_id(target) -> int:
    return int(target.parent_id or target.id)


@adds.handle()
async def _(target: MsgTarget, account: str):
    group_id = _group_id(target)
    try:
        rsp = await get_account_status(account)
        if rsp["personaname"] == "":
            await UniMessage.text("查询失败！").send(target)
        elif rsp["gameextrainfo"] == "":
            await UniMessage.text("%s 没在玩游戏！" % rsp["personaname"]).send(target)
        else:
            await UniMessage.text(
                "%s 正在玩 %s ！" % (rsp["personaname"], rsp["gameextrainfo"])
            ).send(target)
        await update_steam_ids(account, group_id)
        await UniMessage.text("订阅成功").send(target)
    except Exception as e:
        logger.exception(e)
        await UniMessage.text("订阅失败").send(target)


@dels.handle()
async def _(target: MsgTarget, account: str):
    group_id = _group_id(target)
    try:
        await del_steam_ids(account, group_id)
        await UniMessage.text("删除订阅成功").send(target)
    except Exception as e:
        logger.exception(e)
        await UniMessage.text("删除订阅失败").send(target)


@looks.handle()
async def _(target: MsgTarget):
    group_id = _group_id(target)
    msg = "======steam======\n"
    await update_game_status()
    for key, val in playing_state.items():
        if group_id in sub["subscribes"][str(key)]:
            if val["gameextrainfo"] == "":
                msg += "%s 没在玩游戏\n" % val["personaname"]
            else:
                msg += "%s 正在游玩 %s\n" % (val["personaname"], val["gameextrainfo"])
    await UniMessage.text(msg).send(target)


@look.handle()
async def _(target: MsgTarget, account: str):
    rsp = await get_account_status(account)
    if rsp["personaname"] == "":
        await UniMessage.text("查询失败！").send(target)
    elif rsp["gameextrainfo"] == "":
        await UniMessage.text("%s 没在玩游戏！" % rsp["personaname"]).send(target)
    else:
        await UniMessage.text(
            "%s 正在玩 %s ！" % (rsp["personaname"], rsp["gameextrainfo"])
        ).send(target)


async def get_account_status(id) -> dict:
    id = await format_id(id)
    params = {"key": cfg["key"], "format": "json", "steamids": id}
    try:
        resp = await aiohttpx.get(
            "https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v0002/",
            params=params,
        )
    except Exception as e:
        logger.exception(e)
        logger.error(type(e))
    if not resp.ok:
        logger.exception(f"steam api return error {resp.status_code}")
        return
    rsp = resp.json
    friend = rsp["response"]["players"][0]
    return {
        "personaname": friend["personaname"] if "personaname" in friend else "",
        "gameextrainfo": friend["gameextrainfo"] if "gameextrainfo" in friend else "",
    }


async def update_game_status() -> None:
    if not sub["subscribes"]:
        return
    params = {
        "key": cfg["key"],
        "format": "json",
        "steamids": ",".join(sub["subscribes"].keys()),
    }
    try:
        resp = await aiohttpx.get(
            "https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v0002/",
            params=params,
        )
    except Exception as e:
        logger.exception(e)
        logger.error(type(e))
        return

    if not resp.ok:
        logger.exception(f"steam api return error {resp.status_code}")
        return
    rsp = resp.json
    for friend in rsp["response"]["players"]:
        playing_state[friend["steamid"]] = {
            "personaname": friend["personaname"],
            "gameextrainfo": friend["gameextrainfo"]
            if "gameextrainfo" in friend
            else "",
        }


async def update_steam_ids(steam_id, group):
    steam_id = await format_id(steam_id)
    if steam_id not in sub["subscribes"]:
        sub["subscribes"][str(steam_id)] = []
    if group not in sub["subscribes"][str(steam_id)]:
        sub["subscribes"][str(steam_id)].append(group)
    with subscribe_file.open(mode="w") as fil:
        json.dump(sub, fil, indent=4, ensure_ascii=False)
    await update_game_status()


async def del_steam_ids(steam_id, group):
    steam_id = await format_id(steam_id)
    if group in sub["subscribes"][str(steam_id)]:
        sub["subscribes"][str(steam_id)].remove(group)
    with subscribe_file.open(mode="w") as fil:
        json.dump(sub, fil, indent=4, ensure_ascii=False)
    await update_game_status()


@scheduled_job("cron", minute="*/2", id="推送steam", jitter=10)
async def check_steam_status():
    if not playing_state:
        await update_game_status()
        return
    old_state = playing_state.copy()
    await update_game_status()
    await sleep(0.5)
    for key, val in playing_state.items():
        if val["gameextrainfo"] != old_state[key]["gameextrainfo"]:
            enabled_groups = await sv.get_enable_groups()
            glist = set(sub["subscribes"][key]) & set(enabled_groups)
            if val["gameextrainfo"] == "":
                await broadcast(
                    {group: enabled_groups[group] for group in glist},
                    "%s 不玩 %s 了！"
                    % (val["personaname"], old_state[key]["gameextrainfo"]),
                )
            else:
                await broadcast(
                    {group: enabled_groups[group] for group in glist},
                    "%s 开始游玩 %s ！" % (val["personaname"], val["gameextrainfo"]),
                )


async def broadcast(group_bots: dict[int, Iterable[Bot]], msg):
    for group, bots in group_bots.items():
        for bot in bots:
            await send_to_target(bot, group_target(group), msg)
            await sleep(0.5)
