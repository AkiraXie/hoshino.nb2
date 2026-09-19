from nonebot.params import Depends
from sqlalchemy import select

from hoshino import hsn_nickname
from hoshino.core.permission import SUPERUSER
from hoshino.platform.depends import GroupID, GroupMemberName, ParamText
from hoshino.platform.permission import ADMIN

from .util import (
    AlistenClient,
    AlistenConfig,
    AlistenCookieError,
    Session,
    get_client,
    get_config,
    sv,
    update_client,
)

configset = sv.on_command("听歌房配置", aliases={"alistenconfig"}, permission=ADMIN)
configshow = sv.on_command("听歌房显示配置", aliases={"alistenshowconfig"}, permission=ADMIN)
configtoken = sv.on_command(
    "听歌房token",
    aliases={"alistentoken"},
    permission=SUPERUSER,
)
cookiecmd = sv.on_command(
    "听歌房cookie",
    aliases={"alistencookie", "听歌房ck"},
    permission=SUPERUSER,
)


@configset.handle()
async def _(text: str = ParamText(), gid: int = GroupID()):
    msgs = text.strip().split()
    if len(msgs) not in (3, 4):
        await configset.finish("请检查参数个数")
    if len(msgs) == 3:
        email, server_url, house_id = msgs
        house_password = ""
    else:
        email, server_url, house_id, house_password = msgs
    with Session() as session:
        stmt = select(AlistenConfig).where(AlistenConfig.gid == gid)
        result = session.execute(stmt)
        config = result.scalar_one_or_none()
        if config:
            config.server_url = server_url
            config.house_id = house_id
            config.house_password = house_password
            config.gemail = email
        else:
            config = AlistenConfig(
                gid=gid,
                gemail=email,
                server_url=server_url,
                house_id=house_id,
                house_password=house_password,
            )
            session.add(config)
        session.commit()
        update_client(config)
    await configset.finish(
        f"听歌房配置已更新\n服务器地址: {server_url}\n房间ID: {house_id}\n群 email: {email}\n"
    )


@configshow.handle()
async def _(config: AlistenConfig | None = Depends(get_config)):
    if not config:
        await configshow.finish("当前没有配置听歌房")
    token_hint = "已配置" if (config.token or "").strip() else "未配置"
    await configshow.finish(
        "听歌房配置如下\n"
        f"服务器地址: {config.server_url}\n"
        f"房间ID: {config.house_id}\n"
        f"房间密码: {config.house_password}\n"
        f"token: {token_hint}\n"
    )


@configtoken.handle()
async def _(
    text: str = ParamText(),
    config: AlistenConfig | None = Depends(get_config),
):
    if not config:
        await configtoken.finish("当前没有配置听歌房")
    token = text.strip()
    if not token:
        await configtoken.finish("用法: 听歌房token <token>")
    with Session() as session:
        stmt = select(AlistenConfig).where(AlistenConfig.gid == config.gid)
        row = session.execute(stmt).scalar_one_or_none()
        if not row:
            await configtoken.finish("当前没有配置听歌房")
        row.token = token
        session.commit()
        update_client(row)
    await configtoken.finish("听歌房 token 已更新")


@cookiecmd.handle()
async def _(
    text: str = ParamText(),
    client: AlistenClient | None = Depends(get_client),
):
    if not client:
        await cookiecmd.finish("当前没有配置听歌房")
    cookie = text.strip()
    try:
        if not cookie:
            status = await client.cookie_status()
            hint = "已设置" if status.is_set else "未设置"
            await cookiecmd.finish(f"听歌房 cookie {hint}")
        result = await client.set_cookie(cookie)
    except AlistenCookieError as exc:
        await cookiecmd.finish(exc.reason)
    persist_hint = "并已持久化" if result.persisted else "（运行时已生效，但持久化失败）"
    await cookiecmd.finish(f"听歌房 cookie 已更新{persist_hint}")


pickmusic = sv.on_command("点歌", aliases={"pickmusic"}, compact=False)
pickmusicid = sv.on_command("id点歌", aliases={"idpickmusic", "ID点歌", "Id点歌"}, compact=False)
houseuser = sv.on_command("听歌房用户", aliases={"alistenusers", "听歌房成员", "谁在听歌"})
playlistcmd = sv.on_command(
    "播放列表",
    aliases={
        "alistenplaylist",
        "听歌房歌曲",
    },
)


@pickmusic.handle()
async def _(
    text: str = ParamText(),
    user_name: str = GroupMemberName(default=hsn_nickname),
    client: AlistenClient | None = Depends(get_client),
):
    if not client:
        await pickmusic.finish("当前没有配置听歌房")
    source = "wy"
    name = text.strip()
    if ":" in name:
        parts = name.split(":", 1)
        if len(parts) == 2 and parts[0] in ["wy", "qq", "db"]:
            source = parts[0]
            name = parts[1]
    elif name.startswith("BV"):
        source = "db"
    resp = await client.pick_music(name=name, source=source, user_name=user_name)
    if resp:
        sv.logger.debug(f"点歌结果: {resp}")
        msg = "点歌成功！歌曲已加入播放列表"
        msg += f"\n歌曲：{resp.name}"
        msg += f"\n歌手：{resp.artist}" if resp.artist != "unknown" else ""
        source_name = {
            "wy": "网易云音乐",
            "qq": "QQ音乐",
            "db": "Bilibili",
        }.get(resp.source, resp.source)
        msg += f"\n来源：{source_name}"
        await pickmusic.finish(msg, call_header=True)
    else:
        await pickmusic.finish("点歌失败!", call_header=True)


@pickmusicid.handle()
async def _(
    text: str = ParamText(),
    user_name: str = GroupMemberName(default=hsn_nickname),
    client: AlistenClient | None = Depends(get_client),
):
    if not client:
        await pickmusicid.finish("当前没有配置听歌房")
    source = "wy"
    name = text.strip()
    if ":" in name:
        parts = name.split(":", 1)
        if len(parts) == 2 and parts[0] in ["wy", "qq", "db"]:
            source = parts[0]
            name = parts[1]
    if not name.isdigit():
        await pickmusicid.finish("请用数字 ID 点歌")
    resp = await client.pick_music(id_=name, source=source, user_name=user_name)
    if resp:
        msg = "点歌成功！歌曲已加入播放列表"
        msg += f"\n歌曲：{resp.name}"
        msg += f"\n歌手：{resp.artist}"
        source_name = {
            "wy": "网易云音乐",
            "qq": "QQ音乐",
            "db": "Bilibili",
        }.get(resp.source, resp.source)
        msg += f"\n来源：{source_name}"
        await pickmusicid.finish(msg, call_header=True)
    else:
        await pickmusicid.finish("点歌失败!", call_header=True)


@houseuser.handle()
async def _(client: AlistenClient | None = Depends(get_client)):
    if not client:
        await houseuser.finish("当前没有配置听歌房")
    resp = await client.house_houseuser()
    if resp is None:
        await houseuser.finish("获取房间用户请求失败")
    if not resp:
        await houseuser.finish("当前没有人听歌哦")
    msg = "当前听歌房用户列表：\n"
    msg += "\n".join(f"{user.name} <{user.email}>" for user in resp)
    await houseuser.finish(msg, call_header=True)


@playlistcmd.handle()
async def _(client: AlistenClient | None = Depends(get_client)):
    if not client:
        await playlistcmd.finish("当前没有配置听歌房")

    resp = await client.playlist()

    if resp is None:
        await playlistcmd.finish("获取播放列表失败")
    msg = "听歌房播放列表：\n"
    for i, item in enumerate(resp.playlist, 1):
        msg += f"{i}. {item.name}-{item.artist} \n"
    current = await client.current_music()
    if current and current.name:
        m = f"\n正在播放：{current.name}-{current.artist} \n"
        msg = m + msg
    await playlistcmd.finish(msg.strip(), call_header=True)
