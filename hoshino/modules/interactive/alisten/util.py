import os

from pydantic import BaseModel, ConfigDict, Field, RootModel
from sqlalchemy import Integer, Text, create_engine, inspect, select, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from hoshino import db_dir
from hoshino.core.hooks import on_serial_startup, on_startup
from hoshino.platform.depends import GroupID
from hoshino.service import Service
from hoshino.util.aiohttpx import Response, get, post

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
    token: Mapped[str] = mapped_column(Text, nullable=False, default="")


def _ensure_schema() -> None:
    Base.metadata.create_all(engine)
    columns = {column["name"] for column in inspect(engine).get_columns("alisten_config")}
    if "token" not in columns:
        with engine.begin() as conn:
            conn.execute(
                text("ALTER TABLE alisten_config ADD COLUMN token TEXT NOT NULL DEFAULT ''")
            )


@on_serial_startup
async def _ensure_alisten_schema() -> None:
    _ensure_schema()


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


class CookieStatus(BaseModel):
    """GET /config/cookie 响应：只返回是否已设置，不泄露 cookie 值。"""

    model_config = ConfigDict(populate_by_name=True)

    is_set: bool = Field(alias="set")


class SetCookieResult(BaseModel):
    """POST /config/cookie 响应。"""

    message: str
    persisted: bool = True


class AlistenCookieError(Exception):
    """Cookie 管理接口失败。"""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _cookie_error_from_response(resp: Response, fallback: str) -> AlistenCookieError:
    detail = None
    try:
        payload = resp.json
        if isinstance(payload, dict):
            error = payload.get("error")
            if isinstance(error, str) and error.strip():
                detail = error.strip()
    except Exception:
        sv.logger.debug("cookie 接口错误响应不是 JSON")
    if resp.status_code == 401:
        return AlistenCookieError(detail or "token 无效")
    if resp.status_code == 403:
        return AlistenCookieError(detail or "服务端未配置 token")
    if resp.status_code == 400:
        return AlistenCookieError(detail or "请求无效")
    return AlistenCookieError(detail or fallback)


class AlistenClient:
    """Alisten API 客户端"""

    def __init__(self, config: AlistenConfig):
        self.config = config

    def _url(self, endpoint: str) -> str:
        return f"{self.config.server_url.rstrip('/')}{endpoint}"

    def _token(self) -> str:
        return (self.config.token or "").strip()

    def _auth_headers(self) -> dict[str, str]:
        token = self._token()
        if not token:
            return {}
        return {"Authorization": f"Bearer {token}"}

    async def _post(self, endpoint: str, payload: dict | None = None) -> Response:
        url = self._url(endpoint)
        headers = {"Content-Type": "application/json"}
        return await post(
            url,
            json=payload,
            headers=headers,
            # 默认不校验（自建服务证书常自签）；需严格校验时设 HSN_ALISTEN_VERIFY_SSL=1
            verify=verify_ssl_enabled(),
        )

    async def cookie_status(self) -> CookieStatus:
        """查询服务端音乐 Cookie 是否已设置（不返回具体值）。"""
        if not self._token():
            raise AlistenCookieError("未配置 token，无法查询 cookie。先用「听歌房token」设置")
        try:
            resp = await get(
                self._url("/config/cookie"),
                headers=self._auth_headers(),
                verify=verify_ssl_enabled(),
            )
        except Exception as exc:
            sv.logger.exception("Error fetching cookie status", exception=True)
            raise AlistenCookieError("查询 cookie 状态失败") from exc
        if not resp.ok:
            raise _cookie_error_from_response(resp, "查询 cookie 状态失败")
        try:
            return CookieStatus.model_validate(resp.json)
        except Exception as exc:
            sv.logger.exception("Error parsing cookie status", exception=True)
            raise AlistenCookieError("查询 cookie 状态失败") from exc

    async def set_cookie(self, cookie: str) -> SetCookieResult:
        """运行时更新服务端音乐 Cookie，并尽量持久化到 config.json。"""
        if not self._token():
            raise AlistenCookieError("未配置 token，无法设置 cookie。先用「听歌房token」设置")
        try:
            resp = await post(
                self._url("/config/cookie"),
                json={"cookie": cookie},
                headers={
                    "Content-Type": "application/json",
                    **self._auth_headers(),
                },
                verify=verify_ssl_enabled(),
            )
        except Exception as exc:
            sv.logger.exception("Error setting cookie", exception=True)
            raise AlistenCookieError("设置 cookie 失败") from exc
        if not resp.ok:
            raise _cookie_error_from_response(resp, "设置 cookie 失败")
        try:
            return SetCookieResult.model_validate(resp.json)
        except Exception as exc:
            sv.logger.exception("Error parsing set-cookie response", exception=True)
            raise AlistenCookieError("设置 cookie 失败") from exc

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
