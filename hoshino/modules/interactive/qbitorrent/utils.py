import os
import re

from pydantic import BaseModel
from sqlalchemy import Integer, Text, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from hoshino import db_dir
from hoshino.core.hooks import on_serial_startup, on_startup
from hoshino.platform.depends import GroupID
from hoshino.service import Service
from hoshino.util.aiohttpx import get, post

DEFAULT_CATEGORY = "hoshino"
"""qBittorrent 默认分类名"""


def verify_ssl_enabled() -> bool:
    """HTTPS 证书校验开关（默认不校验）。

    自建 qBittorrent 站点证书常为自签/过期，默认关闭校验以保持可用；需要严格
    校验时设置环境变量 ``HSN_QBIT_VERIFY_SSL=1``。与 ``hoshino.util.media`` 的
    ``HSN_MEDIA_VERIFY_SSL`` 约定保持一致。
    """
    return os.getenv("HSN_QBIT_VERIFY_SSL", "0").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


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
    category: Mapped[str] = mapped_column(Text, nullable=True, default=DEFAULT_CATEGORY)


@on_serial_startup
async def _ensure_qbt_schema() -> None:
    Base.metadata.create_all(engine)


async def get_config(gid: int | None = GroupID()) -> QbtConfig | None:
    """获取群组的qBittorrent配置"""
    if gid is None:
        return None
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
    category: str = DEFAULT_CATEGORY
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
                verify=verify_ssl_enabled(),
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
            sv.logger.warning(
                f"qBittorrent 登录失败: status={response.status_code}, body={response.text[:100]}"
            )
            return False
        except Exception:
            sv.logger.exception("qBittorrent 登录异常", exception=True)
            return False

    async def _ensure_login(self) -> bool:
        """确保已登录，若未登录则尝试登录"""
        if self.session_cookie:
            return True
        return await self.login()

    async def _add_torrent_raw(self, url: str, category: str) -> tuple[int, str]:
        """返回 (status_code, 响应文本)。status_code=403 表示 SID 过期需要重新登录"""
        try:
            headers = {"Cookie": f"SID={self.session_cookie}"}
            response = await post(
                f"{self.base_url}/api/v2/torrents/add",
                data={
                    "urls": url,
                    "category": category,
                    "autoTMM": "false",
                },
                headers=headers,
                verify=verify_ssl_enabled(),
            )
            return response.status_code, response.text or ""
        except Exception as e:
            sv.logger.exception("添加种子请求异常", exception=True)
            return -1, str(e)

    async def add_torrent(self, url: str, category: str | None = None) -> dict:
        """添加种子下载；SID 过期时自动重新登录后重试一次"""
        if not await self._ensure_login():
            return {"success": False, "message": "登录失败"}

        cat = category or self.config.category or DEFAULT_CATEGORY
        status, body = await self._add_torrent_raw(url, cat)
        if status == 403:
            sv.logger.info("SID 已过期，尝试重新登录")
            self.session_cookie = None
            if not await self.login():
                return {"success": False, "message": "登录失败"}
            status, body = await self._add_torrent_raw(url, cat)
        if status == -1:
            return {"success": False, "message": f"添加种子时发生错误: {body}"}
        if status != 200:
            return {"success": False, "message": f"请求失败: {status}"}
        return {"success": True, "message": "种子添加成功"}

    async def _fetch_torrents_raw(
        self, category: str | None = None, filter_: str | None = None
    ) -> tuple[int, list[dict]]:
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
                verify=verify_ssl_enabled(),
            )
            if response.status_code == 200:
                return 200, response.json
            return response.status_code, []
        except Exception:
            sv.logger.exception("获取种子列表异常", exception=True)
            return -1, []

    async def get_torrents(
        self, category: str | None = None, filter_: str | None = None
    ) -> list[dict]:
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
    """验证是否为有效的磁力链接（32 或 40 位十六进制 BTIH）"""
    magnet_pattern = r"^magnet:\?xt=urn:btih:(?:[a-fA-F0-9]{32}|[a-fA-F0-9]{40})$"
    return bool(re.match(magnet_pattern, url))


def validate_torrent_url(url: str) -> bool:
    """验证是否为有效的种子文件URL"""
    return url.startswith(("http://", "https://")) and url.endswith(".torrent")


def validate_download_url(url: str) -> tuple[bool, str]:
    """验证下载URL"""
    if validate_magnet_url(url):
        return True, "磁力链接"
    if validate_torrent_url(url):
        return True, "种子文件"
    if url.startswith(("http://", "https://")):
        return True, "网址"
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


def get_client(gid: int | None = GroupID()) -> QbtClient | None:
    if gid is None:
        return None
    return _clients.get(gid)


def update_client(config: QbtConfig):
    _clients[config.gid] = QbtClient(config)


async def add_torrent_download(client: QbtClient, url: str, category: str | None = None) -> dict:
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
    if size > 1024**2:
        return f"{size / (1024**2):.1f} MB"
    return f"{size / 1024:.1f} KB"


async def get_active_torrents(client: QbtClient, category: str | None = None) -> list[dict]:
    """获取活跃种子列表"""
    return await client.get_torrents(category, filter_="active")


async def get_completed_torrents(client: QbtClient, category: str | None = None) -> list[dict]:
    """获取已完成的种子列表"""
    return await client.get_torrents(category, filter_="completed")
