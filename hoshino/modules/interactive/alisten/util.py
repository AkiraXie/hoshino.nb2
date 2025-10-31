from pydantic import BaseModel, RootModel
from sqlalchemy.orm import Mapped, mapped_column, DeclarativeBase, sessionmaker
from sqlalchemy import select, create_engine, Integer, Float, Text
from hoshino import db_dir
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

    name: str
    source: str
    id: str


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


async def pick_music(
    source: str, user_name: str, config: AlistenConfig, id_="", name=""
) -> MusicData | None:
    request = PickMusicRequest(
        houseId=config.house_id,
        password=config.house_password,
        user=User(name=user_name, email=config.gemail),
        id=id_,
        name=name,
        source=source,
    )

    url = f"{config.server_url}/music/pick"
    try:
        response = await post(url, json=request.model_dump(), verify=False)
        response.raise_for_status()
        rj = response.json
        resp = MusicData.model_validate(rj)
        return resp
    except Exception as e:
        sv.logger.error(f"Error picking music: {e}")
        return None


async def house_houseuser(config: AlistenConfig) -> HouseUserResponse | None:
    """获取房间内用户列表

    Returns:
        房间用户列表或错误信息
    """
    request_data = HouseUserRequest(
        houseId=config.house_id,
        password=config.house_password,
    )

    url = f"{config.server_url}/house/houseuser"
    resp = await post(url, json=request_data.model_dump(), verify=False)
    resp.raise_for_status()
    rj = resp.json
    result = HouseUserResponse.model_validate(rj)
    return result
