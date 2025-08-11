from pydantic import BaseModel
from sqlalchemy.orm import Mapped, mapped_column,DeclarativeBase,sessionmaker
from sqlalchemy import select, create_engine
from hoshino import db_dir
from hoshino.permission import SUPERUSER,ADMIN
from hoshino.service import Service
from hoshino.util.aiohttpx import get,post
db_path = db_dir / "bilidata.db"
engine = create_engine(f"sqlite:///{db_path}", echo=False, future=True)
Session = sessionmaker(bind=engine, expire_on_commit=False)
sv = Service("alisten",enable_on_default=False,visible=False)

class Base(DeclarativeBase):
    pass


class AlistenConfig(Base):
    """alisten 配置模型"""

    __tablename__ = "alisten_config"

    gid: Mapped[int] = mapped_column(primary_key=True)
    gemail: Mapped[str] = mapped_column(unique=True)    
    server_url: Mapped[str]
    """alisten 服务器地址"""
    house_id: Mapped[str]
    """房间 ID"""
    house_password: Mapped[str] = mapped_column(default="")
    """房间密码"""

session = sessionmaker(bind=engine)

def get_config(gid:int) -> AlistenConfig | None:
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
        response = await post(url, json=request.dict())
        response.raise_for_status()
        rj = response.json()
        resp = SuccessResponse.model_validate(rj)
        return resp
    except Exception as e:
        sv.logger.error(f"Error picking music: {e}")
        return None 