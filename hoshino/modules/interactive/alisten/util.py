import os

from pydantic import BaseModel, RootModel
from sqlalchemy import Integer, Text, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from hoshino import db_dir
from hoshino.core.hooks import on_serial_startup, on_startup
from hoshino.platform.depends import GroupID
from hoshino.service import Service
from hoshino.util.aiohttpx import Response, post

db_path = db_dir / "alisten.db"
engine = create_engine(f"sqlite:///{db_path}", echo=False, future=True)
Session = sessionmaker(bind=engine, expire_on_commit=False)
sv = Service("alisten", enable_on_default=False, visible=False)


def verify_ssl_enabled() -> bool:
    """HTTPS 证书校验开关（默认不校验）。

    自建 alisten 服务证书常为自签/过期，默认关闭校验以保持可用；需要严格校验时
    设置环境变量 ``HSN_ALISTEN_VERIFY_SSL=1``。与 qbitorrent 的
    ``HSN_QBIT_VERIFY_SSL`` 约定保持一致。
    """
    return os.getenv("HSN_ALISTEN_VERIFY_SSL", "0").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


class Base(DeclarativeBase):
    pass


class AlistenConfig(Base):
    """alisten 配置模型"""

    __tablename__ = "alisten_config"

    gid: Mapped[int] = mapped_column(Integer, primary_key=True)
    gemail: Mapped[str] = mapped_column(Text)
    house_id: Mapped[str] = mapped_column(Text, nullable=False)
    house_password: Mapped[str] = mapped_column(Text, nullable=True)
    server_url: Mapped[str] = mapped_column(Text, nullable=False)


@on_serial_startup
async def _ensure_alisten_schema() -> None:
    Base.metadata.create_all(engine)


async def get_config(gid: int | None = GroupID()) -> AlistenConfig | None:
    if gid is None:
        return None
    with Session() as session:
        stmt = select(AlistenConfig).where(AlistenConfig.gid == gid)
        result = session.execute(stmt)
        return result.scalar_one_or_none()


class MusicData(BaseModel):
    """音乐数据"""

    id: str
    name: str
    source: str
    artist: str = "unknown"


class User(BaseModel):
    name: str
    email: str | None = None


class HouseUserRequest(BaseModel):
    """获取房间用户请求"""

    houseId: str
    password: str = ""


class HouseUserResponse(RootModel[list[User]]):
    """房间用户列表响应"""

    def __iter__(self):
        return iter(self.root)

    def __getitem__(self, item: int):
        return self.root[item]

    def __bool__(self):
        return bool(self.root)


class PickMusicRequest(BaseModel):
    """点歌请求"""

    houseId: str
    password: str = ""
    user: User
    id: str = ""
    name: str = ""
    source: str = "wy"


class CurrentMusicRequest(BaseModel):
    """获取当前音乐请求"""

    houseId: str
    password: str = ""


class CurrentMusicResponse(BaseModel):
    """当前音乐响应"""

    name: str
    source: str
    artist: str
    id: str
    user: User


class PlaylistItem(BaseModel):
    """播放列表项"""

    name: str
    source: str
    artist: str = "unknown"
    id: str
    likes: int
    user: User


class PlaylistRequest(BaseModel):
    """获取播放列表请求"""

    houseId: str
    password: str = ""


class PlaylistResponse(BaseModel):
    """播放列表响应"""

    playlist: list[PlaylistItem] | None = None


class AlistenClient:
    """Alisten API 客户端"""

    def __init__(self, config: AlistenConfig):
        self.config = config

    async def _post(self, endpoint: str, payload: dict | None = None) -> Response:
        url = f"{self.config.server_url}{endpoint}"
        headers = {"Content-Type": "application/json"}
        return await post(
            url,
            json=payload,
            headers=headers,
            # 默认不校验（自建服务证书常自签）；需严格校验时设 HSN_ALISTEN_VERIFY_SSL=1
            verify=verify_ssl_enabled(),
        )

    async def pick_music(
        self, user_name: str, id_: str = "", name: str = "", source: str = "wy"
    ) -> MusicData | None:
        request = PickMusicRequest(
            houseId=self.config.house_id,
            password=self.config.house_password,
            user=User(name=user_name, email=self.config.gemail),
            id=id_,
            name=name,
            source=source,
        )
        try:
            response = await self._post("/music/pick", payload=request.model_dump())
            response.raise_for_status()
            rj = response.json
            sv.logger.debug(f"点歌接口响应: {rj}")
            data = MusicData.model_validate(rj)
            sv.logger.debug(f"点歌解析结果: {data}")
            return data
        except Exception:
            sv.logger.exception("Error picking music", exception=True)
            return None

    async def house_houseuser(self) -> HouseUserResponse | None:
        request_data = HouseUserRequest(
            houseId=self.config.house_id,
            password=self.config.house_password,
        )
        try:
            resp = await self._post("/house/houseuser", payload=request_data.model_dump())
            resp.raise_for_status()
            rj = resp.json
            return HouseUserResponse.model_validate(rj)
        except Exception:
            sv.logger.exception("Error fetching house users", exception=True)
            return None

    async def current_music(self) -> CurrentMusicResponse | None:
        request_data = CurrentMusicRequest(
            houseId=self.config.house_id,
            password=self.config.house_password,
        )
        try:
            resp = await self._post("/music/sync", payload=request_data.model_dump())
            resp.raise_for_status()
            rj = resp.json
            return CurrentMusicResponse.model_validate(rj)
        except Exception:
            sv.logger.exception("Error fetching current music", exception=True)
            return None

    async def playlist(self) -> PlaylistResponse | None:
        request_data = PlaylistRequest(
            houseId=self.config.house_id,
            password=self.config.house_password,
        )
        try:
            resp = await self._post("/music/playlist", payload=request_data.model_dump())
            resp.raise_for_status()
            rj = resp.json
            sv.logger.debug(f"播放列表接口响应: {rj}")
            return PlaylistResponse.model_validate(rj)
        except Exception:
            sv.logger.exception("Error fetching playlist", exception=True)
            return None


_clients: dict[int, AlistenClient] = {}


@on_startup
async def init_alisten_clients():
    with Session() as session:
        stmt = select(AlistenConfig)
        configs = session.scalars(stmt).all()
        for config in configs:
            _clients[config.gid] = AlistenClient(config)
    sv.logger.info(f"Initialized {len(_clients)} alisten clients")


def get_client(gid: int | None = GroupID()) -> AlistenClient | None:
    if gid is None:
        return None
    return _clients.get(gid)


def update_client(config: AlistenConfig):
    _clients[config.gid] = AlistenClient(config)
