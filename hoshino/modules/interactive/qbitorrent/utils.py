from pydantic import BaseModel
from sqlalchemy.orm import Mapped, mapped_column, DeclarativeBase, sessionmaker
from sqlalchemy import select, create_engine, Integer, Text
from hoshino import db_dir
from hoshino.service import Service
from hoshino.util.aiohttpx import post, get
from hoshino.event import GroupMessageEvent
import re

db_path = db_dir / "qbitorrent.db"
engine = create_engine(f"sqlite:///{db_path}", echo=False, future=True)
Session = sessionmaker(bind=engine, expire_on_commit=False)
sv = Service("qbitorrent", enable_on_default=False, visible=False, 
             help_="qBittorrent 种子下载管理\n配置: qbt配置 <服务器地址> <用户名> <密码>\n下载: 添加种子 <磁力链接或种子URL>")


class Base(DeclarativeBase):
    pass


class QbtConfig(Base):
    """qBittorrent 配置模型"""

    __tablename__ = "qbt_config"

    gid: Mapped[int] = mapped_column(Integer, primary_key=True)
    server_url: Mapped[str] = mapped_column(Text, nullable=False)
    username: Mapped[str] = mapped_column(Text, nullable=False)
    password: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(Text, nullable=True, default="hoshino")


Base.metadata.create_all(engine)


async def get_config(event: GroupMessageEvent) -> QbtConfig | None:
    """获取群组的qBittorrent配置"""
    gid = event.group_id
    with Session() as session:
        stmt = select(QbtConfig).where(QbtConfig.gid == gid)
        result = session.execute(stmt)
        return result.scalar_one_or_none()


class QbtLoginRequest(BaseModel):
    """qBittorrent登录请求"""
    username: str
    password: str


class QbtAddTorrentRequest(BaseModel):
    """添加种子请求"""
    urls: str = ""
    category: str = "hoshino"
    autoTMM: str = "false"


class QbtTorrentInfo(BaseModel):
    """种子信息"""
    hash: str
    name: str
    size: int
    progress: float
    state: str
    category: str


class QbtClient:
    """qBittorrent Web API 客户端"""
    
    def __init__(self, config: QbtConfig):
        self.config = config
        self.session_cookie = None
        self.base_url = config.server_url.rstrip('/')
        
    async def login(self) -> bool:
        """登录到qBittorrent"""
        try:
            login_data = {
                'username': self.config.username,
                'password': self.config.password
            }
            
            response = await post(
                f"{self.base_url}/api/v2/auth/login",
                data=login_data,
                verify=False
            )
            
            if response.status_code == 200:
                # 获取会话cookie
                cookies = response.cookies
                if 'SID' in cookies:
                    self.session_cookie = cookies['SID']
                    return True
            return False
            
        except Exception as e:
            sv.logger.error(f"qBittorrent登录失败: {e}")
            return False
    
    async def add_torrent(self, url: str, category: str = None) -> dict:
        """添加种子下载"""
        if not self.session_cookie:
            if not await self.login():
                return {"success": False, "message": "登录失败"}
        
        try:
            # 准备数据
            data = {
                'urls': url,
                'category': category or self.config.category or "hoshino",
                'autoTMM': 'false'
            }
            
            headers = {
                'Cookie': f'SID={self.session_cookie}'
            }
            
            response = await post(
                f"{self.base_url}/api/v2/torrents/add",
                data=data,
                headers=headers,
                verify=False
            )
            
            if response.status_code == 200:
                response_text = response.text
                if response_text == "Ok.":
                    return {"success": True, "message": "种子添加成功"}
                else:
                    return {"success": False, "message": f"添加失败: {response_text}"}
            else:
                return {"success": False, "message": f"请求失败: {response.status_code}"}
                
        except Exception as e:
            sv.logger.error(f"添加种子失败: {e}")
            return {"success": False, "message": f"添加种子时发生错误: {str(e)}"}
    
    async def get_torrents(self, category: str = None) -> list[dict]:
        """获取种子列表"""
        if not self.session_cookie:
            if not await self.login():
                return []
        
        try:
            headers = {
                'Cookie': f'SID={self.session_cookie}'
            }
            
            params = {}
            if category:
                params['category'] = category
            
            response = await get(
                f"{self.base_url}/api/v2/torrents/info",
                headers=headers,
                params=params,
                verify=False
            )
            
            if response.status_code == 200:
                return response.json
            else:
                return []
                
        except Exception as e:
            sv.logger.error(f"获取种子列表失败: {e}")
            return []


def validate_magnet_url(url: str) -> bool:
    """验证是否为有效的磁力链接"""
    magnet_pattern = r'^magnet:\?xt=urn:btih:[a-fA-F0-9]{32}|[a-fA-F0-9]{40}'
    return bool(re.match(magnet_pattern, url))


def validate_torrent_url(url: str) -> bool:
    """验证是否为有效的种子文件URL"""
    return url.startswith(('http://', 'https://')) and url.endswith('.torrent')


def validate_download_url(url: str) -> tuple[bool, str]:
    """验证下载URL"""
    if validate_magnet_url(url):
        return True, "磁力链接"
    elif validate_torrent_url(url):
        return True, "种子文件"
    elif url.startswith(('http://', 'https://')):
        return True, "网址"
    else:
        return False, "无效格式"


async def add_torrent_download(config: QbtConfig, url: str, category: str = None) -> dict:
    """添加种子下载"""
    # 验证URL
    is_valid, url_type = validate_download_url(url)
    if not is_valid:
        return {"success": False, "message": "无效的下载链接格式"}
    
    client = QbtClient(config)
    result = await client.add_torrent(url, category)
    
    if result["success"]:
        result["url_type"] = url_type
    
    return result


async def get_torrent_list(config: QbtConfig, category: str = None) -> list[dict]:
    """获取种子列表"""
    client = QbtClient(config)
    return await client.get_torrents(category)