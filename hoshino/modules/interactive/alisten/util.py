from pydantic import BaseModel, RootModel
from sqlalchemy.orm import Mapped, mapped_column, DeclarativeBase, sessionmaker
from sqlalchemy import select, create_engine, Integer, Float, Text
from hoshino import db_dir
from hoshino.hooks import on_startup
from hoshino.service import Service
from hoshino.util.aiohttpx import post
from hoshino.event import GroupMessageEvent

db_path = db_dir / "alisten.db"
engine = create_engine(f"sqlite:///{db_path}", echo=False, future=True)
Session = sessionmaker(bind=engine, expire_on_commit=False)
sv = Service("alisten", enable_on_default=False, visible=False)


class Base(DeclarativeBase):
    pass


class AlistenConfig(Base):
    """alisten 配置模型"""

    __tablename__ = "alisten_config"

    gid: Mapped[int] = mapped_column(Integer, primary_key=True)
    gemail: Mapped[int] = mapped_column(Text)
    house_id: Mapped[str] = mapped_column(Text, nullable=False)
    house_password: Mapped[str] = mapped_column(Text, nullable=True)
    server_url: Mapped[str] = mapped_column(Text, nullable=False)


Base.metadata.create_all(engine)


async def get_config(event: GroupMessageEvent) -> AlistenConfig | None:
    gid = event.group_id
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

    async def post(self, endpoint: str, json:dict|None = None)  :
        url = f"{self.config.server_url}{endpoint}"
        headers = {"Content-Type": "application/json"}
        return await post(url, json=json, headers=headers,verify=False)

    async def pick_music(self, user_name: str, id_: str = "", name: str = "", source: str = "wy") -> MusicData | None:
        request = PickMusicRequest(
            houseId=self.config.house_id,
            password=self.config.house_password,
            user=User(name=user_name, email=self.config.gemail),
            id=id_,
            name=name,
            source=source,
        )
        try:
            response = await self.post("/music/pick", json=request.model_dump())
            response.raise_for_status()
            rj = response.json
            print(rj)
            data = MusicData.model_validate(rj)
            print(data)
            return data
        except Exception as e:
            sv.logger.error(f"Error picking music: {e}")
            return None
    
    async def house_houseuser(self) -> HouseUserResponse | None:
        request_data = HouseUserRequest(
            houseId=self.config.house_id,
            password=self.config.house_password,
        )
        try:
            resp = await self.post("/house/houseuser", json=request_data.model_dump())
            resp.raise_for_status()
            rj = resp.json
            return HouseUserResponse.model_validate(rj)
        except Exception as e:
            sv.logger.error(f"Error fetching house users: {e}")
            return None
    
    async def current_music(self) -> CurrentMusicResponse | None:
        request_data = CurrentMusicRequest(
            houseId=self.config.house_id,
            password=self.config.house_password,
        )
        try:
            resp = await self.post("/music/sync", json=request_data.model_dump())
            resp.raise_for_status()
            rj = resp.json
            return CurrentMusicResponse.model_validate(rj)
        except Exception as e:
            sv.logger.error(f"Error fetching current music: {e}")
            return None

    async def playlist(self) -> PlaylistResponse | None:
        request_data = PlaylistRequest(
            houseId=self.config.house_id,
            password=self.config.house_password,
        )
        try:
            resp = await self.post("/music/playlist", json=request_data.model_dump())
            resp.raise_for_status()
            rj = resp.json
            print(rj)
            return PlaylistResponse.model_validate(rj)
        except Exception as e:
            sv.logger.error(f"Error fetching playlist: {e}")
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


def get_client(event: GroupMessageEvent) -> AlistenClient | None:
    return _clients.get(event.group_id)


def update_client(config: AlistenConfig):
    _clients[config.gid] = AlistenClient(config)


# async def pick_music(
#     source: str, user_name: str, config: AlistenConfig, id_="", name=""
# ) -> MusicData | None:
#     request = PickMusicRequest(
#         houseId=config.house_id,
#         password=config.house_password,
#         user=User(name=user_name, email=config.gemail),
#         id=id_,
#         name=name,
#         source=source,
#     )

#     url = f"{config.server_url}/music/pick"
#     try:
#         response = await post(url, json=request.model_dump(), verify=False)
#         response.raise_for_status()
#         rj = response.json
#         resp = MusicData.model_validate(rj)
#         return resp
#     except Exception as e:
#         sv.logger.error(f"Error picking music: {e}")
#         return None


# async def house_houseuser(config: AlistenConfig) -> HouseUserResponse | None:
#     """获取房间内用户列表

#     Returns:
#         房间用户列表或错误信息
#     """
#     request_data = HouseUserRequest(
#         houseId=config.house_id,
#         password=config.house_password,
#     )

#     url = f"{config.server_url}/house/houseuser"
#     resp = await post(url, json=request_data.model_dump(), verify=False)
#     resp.raise_for_status()
#     rj = resp.json
#     result = HouseUserResponse.model_validate(rj)
#     return result
