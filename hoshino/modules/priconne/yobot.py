"""
Author: AkiraXie
LastEditors: AkiraXie
GitHub: https://github.com/AkiraXie
"""
import sqlite3
import time
from hoshino import Service, Bot, Event

pcr_time_offset = {
    "jp": 4,
    "tw": 3,
    "kr": 4,
    "cn": 3,
}


def pcr_datetime(area: str) -> int:
    ts = int(time.time())
    ts += pcr_time_offset[area] * 3600
    return ts // 86400


sv = Service("yobot")
try:
    cfg = sv.config
    dbpath: str = cfg["database_path"]  # yobot数据库绝对路径
except:
    sv.logger.warning("识别不到yobot数据库")
weidao = sv.on_command("查尾刀")


@weidao
async def _(bot: Bot, event: Event):
    gid = event.group_id
    try:
        conn = sqlite3.connect(dbpath)
    except:
        await weidao.finish("连接yobot数据库失败")
    groupsql = f"""
    select battle_id,game_server
    from Clan_group
    where Clan_group.group_id={gid}
    limit 1
    """
    groupcur = conn.execute(groupsql)
    for g in groupcur:
        group_bid: int = g[0]
        group_server: str = g[1]
        break
    pcrdate = pcr_datetime(group_server)
    groupclansql = f"""
    select qqid,boss_cycle,boss_num,challenge_pcrtime
    from Clan_challenge
    where is_continue=0 and boss_health_ramain=0 and challenge_pcrdate={pcrdate} 
        and gid={gid} and bid={group_bid} 
    """
    msg = []
    retcur = conn.execute(groupclansql)
    userdic = dict()
    for ret in retcur:
        uid = ret[0]
        boss_cycle = ret[1]
        bossnum = ret[2]
        tm = ret[3]
        userdic[uid] = (boss_cycle, bossnum, tm)  # 保持最新的尾刀信息
    for uid in userdic:
        cycle = userdic[uid][0]
        num = userdic[uid][1]
        tm = userdic[uid][2]
        flagsql = f"""select * from Clan_challenge where is_continue=1 
            and challenge_pcrdate={pcrdate} and gid={gid} and bid={group_bid} 
            and challenge_pcrtime>{tm} and qqid={uid}"""  # 判断尾刀是否有余刀
        flagcur = conn.execute(flagsql)
        if len(list(flagcur)):
            continue
        usersql = "select nickname from User where qqid={}".format(uid)
        usercur = conn.execute(usersql)
        for user in usercur:
            nickname = user[0]
        msg.append(f"{nickname} 第{cycle}周目{num}王尾刀")
    conn.close()
    if not msg:
        await weidao.finish("本群今日无人有尾刀~")
    await weidao.send("\n".join(msg))
