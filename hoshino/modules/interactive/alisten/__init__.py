from sqlalchemy import select
from .util import AlistenConfig, get_config, sv,Session,pick_music
from hoshino.permission import ADMIN
from hoshino import Bot,Event,hsn_nickname
from hoshino.event import GroupMessageEvent
from nonebot.params import Depends
configset = sv.on_command("听歌房配置", aliases={"alistenconfig"}, permission=ADMIN)
configshow = sv.on_command("听歌房显示配置", aliases={"alistenshowconfig"}, permission=ADMIN)

@configset
async def _(bot: Bot, event: GroupMessageEvent):
    msgs= event.get_plaintext().strip().split()
    if len(msgs) not in (3,4):
        await configset.finish("请检查参数个数")
    if len(msgs) == 3:
        email, server_url, house_id = msgs
        house_password = ""
    else:
        email, server_url, house_id, house_password = msgs
    with Session() as session:
        gid = event.group_id
        stmt = select(AlistenConfig).where(AlistenConfig.gid == gid)
        result = session.execute(stmt)
        config = result.scalar_one_or_none()
        if config:
            config.server_url = server_url
            config.house_id = house_id
            config.house_password = house_password
            config.gemail = email
        else:
            newconfig = AlistenConfig(
                gid=event.group_id,
                gemail=email,
                server_url=server_url,
                house_id=house_id,
                house_password=house_password
            )
            session.add(newconfig)
        session.commit()
    await configset.finish("听歌房配置已更新\n"
        f"服务器地址: {server_url}\n"
        f"房间ID: {house_id}\n"
        f"群 email: {email}\n")

@configshow
async def _(bot: Bot, event: GroupMessageEvent, config: AlistenConfig | None = Depends(get_config)):
    if not config:
        await configshow.finish("当前没有配置听歌房")
    await configshow.finish("听歌房配置如下\n"
        f"服务器地址: {config.server_url}\n"
        f"房间ID: {config.house_id}\n"
        f"房间密码: {config.house_password}\n")

pickmusic = sv.on_command("点歌", aliases={"pickmusic"},force_whitespace=True)
pickmusicid = sv.on_command("id点歌", aliases={"idpickmusic","ID点歌","Id点歌"},force_whitespace=True)


async def get_user_name(bot: Bot, event: GroupMessageEvent) -> str:
    info = await bot.get_group_member_info(
        group_id=event.group_id, user_id=event.user_id, no_cache=True
    )
    user_name = hsn_nickname
    for i in (info["card"], info["nickname"]):
        if i:
            user_name = i
            break
    return user_name

@pickmusic
async def _(event: GroupMessageEvent,user_name: str = Depends(get_user_name), config: AlistenConfig | None = Depends(get_config)):
        if not config:
            await pickmusic.finish("当前没有配置听歌房")
        source = "wy"
        name = event.get_plaintext().strip()
        if ":" in name:
            # 格式如 "wy:song_name" 或 "qq:song_name"
            parts = name.split(":", 1)
            if len(parts) == 2 and parts[0] in ["wy", "qq", "db"]:
                source = parts[0]
                name = parts[1]
        elif name.startswith("BV"):
            # Bilibili BV号
            source = "db"
        resp = await pick_music(name=name, source=source, user_name=user_name, config=config)
        if resp:
            msg = "点歌成功！歌曲已加入播放列表"
            msg += f"\n歌曲：{resp.data.name}"
            source_name = {
                "wy": "网易云音乐",
                "qq": "QQ音乐",
                "db": "Bilibili",
            }.get(resp.data.source, resp.data.source)
            msg += f"\n来源：{source_name}"
            await pickmusic.finish(msg,call_header=True)
        else:
            await pickmusic.finish("点歌失败!",call_header=True)

@pickmusicid
async def _(event: GroupMessageEvent, user_name: str = Depends(get_user_name), config: AlistenConfig | None = Depends(get_config)):
    if not config:
        await pickmusic.finish("当前没有配置听歌房")
    source = "wy"
    name = event.get_plaintext().strip()
    if ":" in name:
        # 格式如 "wy:song_name" 或 "qq:song_name"
        parts = name.split(":", 1)
        if len(parts) == 2 and parts[0] in ["wy", "qq", "db"]:
            source = parts[0]
            name = parts[1]
    if not name.isdigit():
        await pickmusic.finish("请用数字 ID 点歌")
    resp = await pick_music(id_=name, source=source, user_name=user_name, config=config)
    if resp:
        msg = "点歌成功！歌曲已加入播放列表"
        msg += f"\n歌曲：{resp.data.name}"
        source_name = {
            "wy": "网易云音乐",
            "qq": "QQ音乐",
            "db": "Bilibili",
        }.get(resp.data.source, resp.data.source)
        msg += f"\n来源：{source_name}"
        await pickmusic.finish(msg,call_header=True)
    else:
        await pickmusic.finish("点歌失败!",call_header=True)