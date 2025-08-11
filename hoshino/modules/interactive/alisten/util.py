from pydantic import BaseModel
from sqlalchemy.orm import Mapped, mapped_column,DeclarativeBase,sessionmaker
from sqlalchemy import select, create_engine,Integer, Float, Text
from hoshino import db_dir
from hoshino.service import Service
from hoshino.util.aiohttpx import post
from hoshino.event import GroupMessageEvent
db_path = db_dir / "alisten.db"
engine = create_engine(f"sqlite:///{db_path}", echo=False, future=True)
Session = sessionmaker(bind=engine, expire_on_commit=False)
sv = Service("alisten",enable_on_default=False,visible=False)

class Base(DeclarativeBase):
    pass


class AlistenConfig(Base):
    """alisten 配置模型"""

    __tablename__ = "alisten_config"

    gid: Mapped[int] = mapped_column(Integer,primary_key=True)
    gemail: Mapped[int] = mapped_column(Text)
    house_id: Mapped[str] = mapped_column(Text, nullable=False)
    house_password: Mapped[str] = mapped_column(Text, nullable=True)
    server_url: Mapped[str] = mapped_column(Text, nullable=False)

Base.metadata.create_all(engine)

async def get_config(event:GroupMessageEvent) -> AlistenConfig | None:
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


class SuccessResponse(BaseModel):
    """成功响应"""

    code: str
    message: str
    data: MusicData



class User(BaseModel):
    name: str
    email: str | None = None

class PickMusicRequest(BaseModel):
    """点歌请求"""

    houseId: str
    housePwd: str = ""
    user: User
    id: str = ""
    name: str = ""
    source: str = "wy"

async def pick_music(source: str, user_name: str, config: AlistenConfig,id_="",name="") -> SuccessResponse | None:

    request = PickMusicRequest(
        houseId=config.house_id,
        housePwd=config.house_password,
        user=User(name=user_name, email=config.gemail),
        id=id_,
        name=name,
        source=source
    )
    
    url = f"{config.server_url}/music/pick"
    try:
        response = await post(url, json=request.model_dump(),verify=False)
        response.raise_for_status()
        rj = response.json
        resp = SuccessResponse.model_validate(rj)
        return resp
    except Exception as e:
        sv.logger.error(f"Error picking music: {e}")
        return None 