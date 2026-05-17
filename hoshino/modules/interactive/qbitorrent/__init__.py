from sqlalchemy import select
from .utils import (
    QbtConfig,
    get_config,
    get_client,
    update_client,
    sv,
    Session,
    add_torrent_download,
    get_active_torrents,
    get_completed_torrents,
    validate_download_url,
    format_size,
    QbtClient,
)
from hoshino.permission import ADMIN
from hoshino.types import Bot
from hoshino.event import GroupMessageEvent
from nonebot.params import Depends

# 配置命令
configset = sv.on_command(
    "qbt配置", aliases={"qbitorrent配置", "qbtconfig"}, permission=ADMIN
)
configshow = sv.on_command(
    "qbt显示配置", aliases={"qbitorrent显示配置", "qbtshowconfig"}, permission=ADMIN
)

# 下载命令
add_torrent = sv.on_command(
    "添加种子", aliases={"下载种子", "qbt下载", "addtorrent"}, force_whitespace=True
)
active_list = sv.on_command("下载列表", aliases={"活跃列表", "qbt列表", "torrents"})
completed_list = sv.on_command("种子列表", aliases={"归档列表", "qbt归档", "completed"})


@configset
async def _(bot: Bot, event: GroupMessageEvent):
    """配置qBittorrent连接信息"""
    msgs = event.get_plaintext().strip().split()
    if len(msgs) not in (3, 4):
        await configset.finish("用法: qbt配置 <服务器地址> <用户名> <密码> [分类]")

    if len(msgs) == 3:
        server_url, username, password = msgs
        category = "hoshino"
    else:
        server_url, username, password, category = msgs

    # 确保服务器地址格式正确
    if not server_url.startswith(("http://", "https://")):
        server_url = f"http://{server_url}"

    with Session() as session:
        gid = event.group_id
        stmt = select(QbtConfig).where(QbtConfig.gid == gid)
        result = session.execute(stmt)
        config = result.scalar_one_or_none()

        if config:
            config.server_url = server_url
            config.username = username
            config.password = password
            config.category = category
            target = config
        else:
            target = QbtConfig(
                gid=event.group_id,
                server_url=server_url,
                username=username,
                password=password,
                category=category,
            )
            session.add(target)
        session.commit()
        update_client(target)

    await configset.finish(
        "qBittorrent配置已更新\n"
        f"服务器地址: {server_url}\n"
        f"用户名: {username}\n"
        f"默认分类: {category}\n"
    )


@configshow
async def _(
    bot: Bot,
    event: GroupMessageEvent,
    config: QbtConfig | None = Depends(get_config),
):
    """显示当前qBittorrent配置"""
    if not config:
        await configshow.finish("当前没有配置qBittorrent")

    await configshow.finish(
        "qBittorrent配置如下\n"
        f"服务器地址: {config.server_url}\n"
        f"用户名: {config.username}\n"
        f"默认分类: {config.category}\n"
    )


@add_torrent
async def _(
    event: GroupMessageEvent,
    client: QbtClient | None = Depends(get_client),
):
    """添加种子下载"""
    if not client:
        await add_torrent.finish("请先使用 'qbt配置' 命令配置qBittorrent连接信息")

    msg_text = event.get_plaintext().strip()
    if not msg_text:
        await add_torrent.finish(
            "用法: 添加种子 <下载链接> [分类]\n"
            "支持格式:\n"
            "- 磁力链接 (magnet:?xt=urn:btih:...)\n"
            "- 种子文件URL (.torrent)\n"
            "- 其他下载链接"
        )

    # 解析参数
    parts = msg_text.split(None, 1)
    if len(parts) == 1:
        url = parts[0]
        category = None
    else:
        url, category = parts

    # 验证URL格式
    is_valid, url_type = validate_download_url(url)
    if not is_valid:
        await add_torrent.finish(
            "无效的下载链接格式！\n"
            "支持的格式:\n"
            "- 磁力链接: magnet:?xt=urn:btih:...\n"
            "- 种子文件: http(s)://.../*.torrent\n"
        )

    # 添加下载任务
    result = await add_torrent_download(client, url, category)
    sv.logger.info(f'添加种子结果: {result}')
    if result["success"]:
        msg = "✅ 种子添加成功！\n"
        msg += f"链接类型: {result.get('url_type', '未知')}\n"
        if result.get("name"):
            msg += f"名称: {result['name']}\n"
            msg += f"大小: {result['size']}\n"
        msg += f"分类: {category or client.config.category or 'hoshino'}"
        await add_torrent.finish(msg, call_header=True)
    else:
        await add_torrent.finish(f"❌ 添加失败: {result['message']}", call_header=True)


STATE_MAP = {
    "downloading": "下载中", "uploading": "上传中",
    "pausedDL": "暂停下载", "pausedUP": "暂停上传",
    "queuedDL": "排队下载", "queuedUP": "排队上传",
    "stalledDL": "停滞下载", "stalledUP": "停滞上传",
    "checkingDL": "检查中", "checkingUP": "检查中",
    "queuedForChecking": "等待检查", "checkingResumeData": "检查数据",
    "moving": "移动中", "unknown": "未知",
    "error": "错误", "missingFiles": "文件缺失",
    "allocating": "分配空间",
}


def _render_torrent_list(torrents: list[dict], max_show: int, title: str, category: str) -> str:
    if not torrents:
        return ""
    msg = f"📋 {title} (分类: {category or '全部'})\n"
    msg += "=" * 30 + "\n"
    for i, t in enumerate(torrents[:max_show]):
        name = t.get("name", "未知")[:30]
        progress = t.get("progress", 0) * 100
        state_cn = STATE_MAP.get(t.get("state", "未知"), t.get("state", "未知"))
        size_str = format_size(t.get("size", 0))
        msg += f"{i + 1}. {name}\n"
        msg += f"   进度: {progress:.1f}% | 状态: {state_cn} | 大小: {size_str}\n"
    if len(torrents) > max_show:
        msg += f"\n... 还有 {len(torrents) - max_show} 个任务未显示"
    return msg


@active_list
async def _(
    event: GroupMessageEvent,
    client: QbtClient | None = Depends(get_client),
):
    if not client:
        await active_list.finish("请先使用 'qbt配置' 命令配置qBittorrent连接信息")

    msg_text = event.get_plaintext().strip()
    max_show = 20
    if msg_text.isdigit():
        max_show = int(msg_text)

    torrents = await get_active_torrents(client, client.config.category)
    if not torrents:
        await active_list.finish("当前没有活跃下载任务")

    msg = _render_torrent_list(torrents, max_show, "活跃下载列表", client.config.category)
    await active_list.finish(msg, call_header=True)


@completed_list
async def _(
    event: GroupMessageEvent,
    client: QbtClient | None = Depends(get_client),
):
    if not client:
        await completed_list.finish("请先使用 'qbt配置' 命令配置qBittorrent连接信息")

    msg_text = event.get_plaintext().strip()
    max_show = 20
    if msg_text.isdigit():
        max_show = int(msg_text)

    torrents = await get_completed_torrents(client, client.config.category)
    if not torrents:
        await completed_list.finish("当前没有已完成的种子")

    msg = _render_torrent_list(torrents, max_show, "已完成种子列表", client.config.category)
    await completed_list.finish(msg, call_header=True)
