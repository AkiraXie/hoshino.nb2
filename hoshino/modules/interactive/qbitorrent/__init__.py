from sqlalchemy import select
from .utils import QbtConfig, get_config, sv, Session, add_torrent_download, get_torrent_list, validate_download_url
from hoshino.permission import ADMIN
from hoshino import Bot
from hoshino.event import GroupMessageEvent
from nonebot.params import Depends

# 配置命令
configset = sv.on_command("qbt配置", aliases={"qbitorrent配置", "qbtconfig"}, permission=ADMIN)
configshow = sv.on_command("qbt显示配置", aliases={"qbitorrent显示配置", "qbtshowconfig"}, permission=ADMIN)

# 下载命令
add_torrent = sv.on_command("添加种子", aliases={"下载种子", "qbt下载", "addtorrent"}, force_whitespace=True)
torrent_list = sv.on_command("种子列表", aliases={"下载列表", "qbt列表", "torrents"})


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
    if not server_url.startswith(('http://', 'https://')):
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
        else:
            newconfig = QbtConfig(
                gid=event.group_id,
                server_url=server_url,
                username=username,
                password=password,
                category=category,
            )
            session.add(newconfig)
        session.commit()
    
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
    config: QbtConfig | None = Depends(get_config),
):
    """添加种子下载"""
    if not config:
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
    result = await add_torrent_download(config, url, category)
    
    if result["success"]:
        msg = "✅ 种子添加成功！\n"
        msg += f"链接类型: {result.get('url_type', '未知')}\n"
        msg += f"分类: {category or config.category or 'hoshino'}"
        await add_torrent.finish(msg, call_header=True)
    else:
        await add_torrent.finish(f"❌ 添加失败: {result['message']}", call_header=True)


@torrent_list
async def _(
    event: GroupMessageEvent,
    config: QbtConfig | None = Depends(get_config),
):
    """显示种子下载列表"""
    if not config:
        await torrent_list.finish("请先使用 'qbt配置' 命令配置qBittorrent连接信息")
    
    # 获取种子列表
    torrents = await get_torrent_list(config, config.category)
    
    if not torrents:
        await torrent_list.finish("当前没有下载任务或获取列表失败")
    
    # 构建消息
    msg = f"📋 种子下载列表 (分类: {config.category or '全部'})\n"
    msg += "=" * 30 + "\n"
    
    # 限制显示数量，避免消息过长
    max_show = 10
    for i, torrent in enumerate(torrents[:max_show]):
        name = torrent.get('name', '未知')[:30]  # 限制名称长度
        progress = torrent.get('progress', 0) * 100
        state = torrent.get('state', '未知')
        size = torrent.get('size', 0)
        
        # 状态转换为中文
        state_map = {
            'downloading': '下载中',
            'uploading': '上传中',
            'pausedDL': '暂停下载',
            'pausedUP': '暂停上传',
            'queuedDL': '排队下载',
            'queuedUP': '排队上传',
            'stalledDL': '停滞下载',
            'stalledUP': '停滞上传',
            'checkingDL': '检查中',
            'checkingUP': '检查中',
            'queuedForChecking': '等待检查',
            'checkingResumeData': '检查数据',
            'moving': '移动中',
            'unknown': '未知',
            'error': '错误',
            'missingFiles': '文件缺失',
            'allocating': '分配空间',
        }
        state_cn = state_map.get(state, state)
        
        # 格式化文件大小
        if size > 1024**3:  # GB
            size_str = f"{size / (1024**3):.1f} GB"
        elif size > 1024**2:  # MB
            size_str = f"{size / (1024**2):.1f} MB"
        else:
            size_str = f"{size / 1024:.1f} KB"
        
        msg += f"{i+1}. {name}\n"
        msg += f"   进度: {progress:.1f}% | 状态: {state_cn} | 大小: {size_str}\n"
    
    if len(torrents) > max_show:
        msg += f"\n... 还有 {len(torrents) - max_show} 个任务未显示"
    
    await torrent_list.finish(msg, call_header=True)