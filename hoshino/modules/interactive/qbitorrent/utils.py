from pydantic import BaseModel
from sqlalchemy.orm import Mapped, mapped_column, DeclarativeBase, sessionmaker
from sqlalchemy import select, create_engine, Integer, Text
import asyncio
import re

from hoshino import db_dir
from hoshino.hooks import on_startup
from hoshino.service import Service
from hoshino.util.aiohttpx import post, get
from hoshino.event import GroupMessageEvent

db_path = db_dir / "qbitorrent.db"
engine = create_engine(f"sqlite:///{db_path}", echo=False, future=True)
Session = sessionmaker(bind=engine, expire_on_commit=False)
sv = Service(
    "qbitorrent",
    enable_on_default=False,
    visible=False,
)


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
        self.base_url = config.server_url.rstrip("/")

    async def login(self) -> bool:
        """登录到qBittorrent，成功返回 True 并设置 session_cookie"""
        try:
            response = await post(
                f"{self.base_url}/api/v2/auth/login",
                data={"username": self.config.username, "password": self.config.password},
                verify=False,
            )
            if response.status_code == 200:
                cookies = response.cookies
                sid = cookies.get("SID")
                if not sid:
                    # 某些情况下 cookie 名可能是小写
                    for k, v in cookies.items():
                        if k.lower() == "sid":
                            sid = v
                            break
                if sid:
                    self.session_cookie = sid
                    return True
            sv.logger.warning(f"qBittorrent 登录失败: status={response.status_code}, body={response.text[:100]}")
            return False
        except Exception as e:
            sv.logger.error(f"qBittorrent 登录异常: {e}")
            return False

    async def _ensure_login(self) -> bool:
        """确保已登录，若未登录则尝试登录"""
        if self.session_cookie:
            return True
        return await self.login()

    async def add_torrent(self, url: str, category: str = None) -> dict:
        """添加种子下载，成功时返回种子名称和大小"""
        if not await self._ensure_login():
            return {"success": False, "message": "登录失败"}

        cat = category or self.config.category or "hoshino"

        try:
            existing_hashes = set()
            _, prev = await self._fetch_torrents_raw(cat)
            for t in prev:
                existing_hashes.add(t.get("hash", ""))

            headers = {"Cookie": f"SID={self.session_cookie}"}
            response = await post(
                f"{self.base_url}/api/v2/torrents/add",
                data={
                    "urls": url,
                    "category": cat,
                    "autoTMM": "false",
                },
                headers=headers,
                verify=False,
            )

            if response.status_code != 200:
                return {"success": False, "message": f"请求失败: {response.status_code}"}

            if response.text != "Ok.":
                return {"success": False, "message": f"添加失败: {response.text}"}

            await asyncio.sleep(0.5)
            _, current = await self._fetch_torrents_raw(cat)
            for t in current:
                if t.get("hash", "") not in existing_hashes:
                    return {
                        "success": True,
                        "message": "种子添加成功",
                        "name": t.get("name", "未知"),
                        "size": format_size(t.get("size", 0)),
                    }

            return {"success": True, "message": "种子添加成功"}

        except Exception as e:
            sv.logger.error(f"添加种子失败: {e}")
            return {"success": False, "message": f"添加种子时发生错误: {str(e)}"}

    async def _fetch_torrents_raw(self, category: str = None, filter_: str = None) -> tuple[int, list[dict]]:
        """返回 (status_code, data)。status_code=403 表示 SID 过期需要重新登录"""
        try:
            headers = {"Cookie": f"SID={self.session_cookie}"}
            params = {}
            if category:
                params["category"] = category
            if filter_:
                params["filter"] = filter_
            response = await get(
                f"{self.base_url}/api/v2/torrents/info",
                headers=headers,
                params=params,
                verify=False,
            )
            if response.status_code == 200:
                return 200, response.json
            return response.status_code, []
        except Exception as e:
            sv.logger.error(f"获取种子列表异常: {e}")
            return -1, []

    async def get_torrents(self, category: str = None, filter_: str = None) -> list[dict]:
        """获取种子列表，自动处理 SID 过期重登录"""
        if not await self._ensure_login():
            return []

        status, data = await self._fetch_torrents_raw(category, filter_)
        if status == 403:
            sv.logger.info("SID 已过期，尝试重新登录")
            self.session_cookie = None
            if not await self.login():
                return []
            status, data = await self._fetch_torrents_raw(category, filter_)
        if status != 200:
            sv.logger.warning(f"获取种子列表失败: status={status}")
        return data if status == 200 else []


def validate_magnet_url(url: str) -> bool:
    """验证是否为有效的磁力链接"""
    magnet_pattern = r"^magnet:\?xt=urn:btih:[a-fA-F0-9]{32}|[a-fA-F0-9]{40}"
    return bool(re.match(magnet_pattern, url))


def validate_torrent_url(url: str) -> bool:
    """验证是否为有效的种子文件URL"""
    return url.startswith(("http://", "https://")) and url.endswith(".torrent")


def validate_download_url(url: str) -> tuple[bool, str]:
    """验证下载URL"""
    if validate_magnet_url(url):
        return True, "磁力链接"
    elif validate_torrent_url(url):
        return True, "种子文件"
    elif url.startswith(("http://", "https://")):
        return True, "网址"
    else:
        return False, "无效格式"


_clients: dict[int, QbtClient] = {}


@on_startup
async def init_qbt_clients():
    with Session() as session:
        stmt = select(QbtConfig)
        configs = session.scalars(stmt).all()
        for config in configs:
            _clients[config.gid] = QbtClient(config)
    sv.logger.info(f"Initialized {len(_clients)} qbitorrent clients")


def get_client(event: GroupMessageEvent) -> QbtClient | None:
    return _clients.get(event.group_id)


def update_client(config: QbtConfig):
    _clients[config.gid] = QbtClient(config)


async def add_torrent_download(
    client: QbtClient, url: str, category: str = None
) -> dict:
    """添加种子下载"""
    is_valid, url_type = validate_download_url(url)
    if not is_valid:
        return {"success": False, "message": "无效的下载链接格式"}

    result = await client.add_torrent(url, category)

    if result["success"]:
        result["url_type"] = url_type

    return result


def format_size(size: int) -> str:
    if size > 1024**3:
        return f"{size / (1024**3):.1f} GB"
    elif size > 1024**2:
        return f"{size / (1024**2):.1f} MB"
    else:
        return f"{size / 1024:.1f} KB"


async def get_active_torrents(client: QbtClient, category: str = None) -> list[dict]:
    """获取活跃种子列表"""
    return await client.get_torrents(category, filter_="active")


async def get_completed_torrents(client: QbtClient, category: str = None) -> list[dict]:
    """获取已完成的种子列表"""
    return await client.get_torrents(category, filter_="completed")
